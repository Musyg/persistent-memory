"""Provenance memory provider for Hermes Agent, backed by hermes-memory-core.

What it adds to Hermes Agent's built-in memory:
- every recalled item is revalidated at read time, so a withdrawn source never reaches the model;
- admission is explicit (a tool call), never an automatic transcript dump;
- a per-session exposure ledger: when a source the session already used is withdrawn, the next
  turn opens with a notice telling the model to stop relying on it.

Install it in the Hermes Agent environment and set ``memory.provider: provenance``. Without
Hermes Agent the module still imports, using the stand-ins in ``_compat``.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

try:  # inside Hermes Agent: its real base class and helpers
    from agent.memory_provider import MemoryProvider, RecallStatus, is_trivial_prompt
    from tools.registry import tool_error
    HERMES_AGENT_AVAILABLE = True
except ImportError:  # plain library use and this repository's checks
    from ._compat import HERMES_AGENT_AVAILABLE, MemoryProvider, RecallStatus, is_trivial_prompt, tool_error

logger = logging.getLogger(__name__)

PROVIDER_NAME = "provenance"
DEFAULTS: dict[str, Any] = {"workspace": "hermes", "prefetch": True, "top_k": 5,
                            "max_context_chars": 2000, "allow_withdraw": True}
KIND_CHOICES = ["observation", "document", "procedure", "task", "hypothesis", "feedback"]

SEARCH_SCHEMA = {
    "name": "provenance_search",
    "description": "Search long-term memory. Every result is checked against current authority at read "
                   "time; withdrawn or superseded sources are never returned. Cite the source_id of any "
                   "result you rely on.",
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "Keywords to look for."},
        "kinds": {"type": "array", "items": {"type": "string", "enum": KIND_CHOICES},
                  "description": "Optional filter on evidence kind."},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 20}},
        "required": ["query"]},
}
REMEMBER_SCHEMA = {
    "name": "provenance_remember",
    "description": "Store one durable fact, decision or procedure the user stated or confirmed. Do not "
                   "store guesses as facts: use kind 'hypothesis' for them. Returns the new source_id.",
    "parameters": {"type": "object", "properties": {
        "text": {"type": "string", "description": "Self-contained statement, with its date if known."},
        "kind": {"type": "string", "enum": KIND_CHOICES, "default": "observation"},
        "aliases": {"type": "array", "items": {"type": "string"},
                    "description": "Optional short names to find it again."}},
        "required": ["text"]},
}
WITHDRAW_SCHEMA = {
    "name": "provenance_withdraw",
    "description": "Withdraw a stored source when the user says it is wrong, outdated or must be "
                   "forgotten. Everything derived from it stops being readable. Not physical erasure.",
    "parameters": {"type": "object", "properties": {
        "source_id": {"type": "string"},
        "reason": {"type": "string", "description": "Why, in a few words."}},
        "required": ["source_id", "reason"]},
}
EXPLAIN_SCHEMA = {
    "name": "provenance_explain",
    "description": "Explain a source: its versions, whether it is readable now, and what depends on it. "
                   "Returns metadata only, not content.",
    "parameters": {"type": "object", "properties": {"source_id": {"type": "string"}},
                   "required": ["source_id"]},
}

SYSTEM_BLOCK = (
    "# Provenance memory\n"
    "Long-term memory with provenance. Use provenance_search before answering about past decisions "
    "or facts, and cite the source_id you rely on. Store a durable fact with provenance_remember only "
    "when the user states or confirms it. If a 'Withdrawn sources' notice appears, stop using "
    "everything that came from those sources, including what you said earlier in this conversation."
)


def config_path(hermes_home: str | os.PathLike[str]) -> Path:
    return Path(hermes_home) / PROVIDER_NAME / "config.json"


def load_config(hermes_home: str | os.PathLike[str]) -> dict[str, Any]:
    try:
        stored = json.loads(config_path(hermes_home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}


def _as_bool(value: Any) -> bool:
    return value if isinstance(value, bool) else str(value).strip().lower() in {"1", "true", "yes", "on"}


def _format_items(items: list[dict[str, Any]]) -> str:
    lines = ["## Provenance memory (validated for this turn)"]
    for item in items:
        ref, meta = item["ref"], item["metadata"]
        lines.append(f"- [{ref['artifact_id']}] ({meta['evidence_kind']}) {item['text']}")
    lines.append("Cite the source_id in brackets when you use one of these.")
    return "\n".join(lines)


def _format_withdrawn(decisions: list[dict[str, Any]]) -> str:
    ids = sorted({d["ref"]["artifact_id"] for d in decisions})
    return ("## Withdrawn sources\n"
            "These sources were used earlier in this conversation and have been withdrawn since: "
            + ", ".join(f"[{i}]" for i in ids)
            + ". Do not rely on, repeat or build on anything that came from them, including your own "
              "earlier answers. If the user asks again, say the information was withdrawn.")


class ProvenanceMemoryProvider(MemoryProvider):
    """One instance per Hermes profile; all state is bound in initialize()."""

    def __init__(self) -> None:
        self._store = None
        self._config: dict[str, Any] = dict(DEFAULTS)
        self._session_id = ""
        self._writes_allowed = True
        self._last_count: Optional[int] = None

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    def is_available(self) -> bool:
        return importlib.util.find_spec("hermes_memory") is not None

    def unavailable_reason(self) -> str:
        return "hermes-memory-core is not installed in Hermes' environment."

    def initialize(self, session_id: str, **kwargs) -> None:
        from .store import Store

        home = kwargs.get("hermes_home")
        if not home:
            raise RuntimeError("hermes_home is required")
        self._config = load_config(home)
        self._store = Store(Path(home) / PROVIDER_NAME, str(self._config["workspace"]))
        self._session_id = session_id or ""
        self._writes_allowed = kwargs.get("agent_context", "primary") in (None, "primary")

    def on_session_switch(self, new_session_id: str, *, parent_session_id: str = "", reset: bool = False,
                          rewound: bool = False, **kwargs) -> None:
        self._session_id = new_session_id or ""

    def system_prompt_block(self) -> str:
        return SYSTEM_BLOCK if self._store is not None else ""

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if self._store is None:
            return ""
        sid = session_id or self._session_id
        parts: list[str] = []
        withdrawn = self._store.withdrawn_since_shown(sid)
        if withdrawn:
            parts.append(_format_withdrawn(withdrawn))
            self._store.mark_notified(sid, [d["ref"] for d in withdrawn])
        self._last_count = None
        if _as_bool(self._config["prefetch"]) and not is_trivial_prompt(query):
            result = self._store.search(query, top_k=int(self._config["top_k"]),
                                        max_chars=int(self._config["max_context_chars"]))
            items = result.get("items", []) if result.get("status") == "completed" else []
            self._last_count = len(items)
            if items:
                self._store.record_exposure(sid, [i["ref"] for i in items], "prefetch")
                parts.append(_format_items(items))
        return "\n\n".join(parts)

    def recall_status(self) -> Optional[RecallStatus]:
        return RecallStatus("Provenance", self._last_count) if self._last_count else None

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "",
                  messages: Optional[list[dict[str, Any]]] = None, **kwargs) -> None:
        """Deliberately empty: admission is explicit, through provenance_remember only."""

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        tools = [SEARCH_SCHEMA, EXPLAIN_SCHEMA]
        if self._writes_allowed:
            tools.append(REMEMBER_SCHEMA)
            if _as_bool(self._config["allow_withdraw"]):
                tools.append(WITHDRAW_SCHEMA)
        return tools

    def handle_tool_call(self, tool_name: str, args: dict[str, Any], **kwargs) -> str:
        if self._store is None:
            return tool_error("provenance memory is not initialized")
        try:
            if tool_name == "provenance_search":
                result = self._store.search(str(args.get("query", "")), kinds=args.get("kinds") or None,
                                            top_k=max(1, min(int(args.get("top_k", 5)), 20)),
                                            max_chars=int(self._config["max_context_chars"]) * 2)
                items = result.get("items", []) if result.get("status") == "completed" else []
                self._store.record_exposure(self._session_id, [i["ref"] for i in items], "tool")
                return json.dumps({"status": result.get("status"), "results": [
                    {"source_id": i["ref"]["artifact_id"], "version_id": i["ref"]["version_id"],
                     "kind": i["metadata"]["evidence_kind"], "text": i["text"]} for i in items]},
                    ensure_ascii=False)
            if tool_name == "provenance_explain":
                return json.dumps(self._store.explain(str(args["source_id"])), ensure_ascii=False)
            if not self._writes_allowed:
                return tool_error("memory writes are disabled outside the primary agent")
            if tool_name == "provenance_remember":
                text = str(args.get("text", "")).strip()
                if not text:
                    return tool_error("text is required")
                return json.dumps(self._store.remember(text, str(args.get("kind") or "observation"),
                                                       args.get("aliases") or None), ensure_ascii=False)
            if tool_name == "provenance_withdraw":
                if not _as_bool(self._config["allow_withdraw"]):
                    return tool_error("withdrawal is disabled in this profile")
                return json.dumps(self._store.withdraw(str(args["source_id"]), str(args.get("reason", ""))[:500],
                                                       self._session_id), ensure_ascii=False)
            return tool_error(f"unknown tool: {tool_name}")
        except LookupError as exc:
            return tool_error(str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            return tool_error(f"invalid request: {exc}")

    def get_config_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "workspace", "description": "Memory workspace for this profile", "default": "hermes"},
            {"key": "prefetch", "description": "Recall validated memory before each turn",
             "default": "true", "choices": ["true", "false"]},
            {"key": "max_context_chars", "description": "Character budget for recalled memory",
             "type": "integer", "default": 2000, "minimum": 200, "maximum": 16000},
            {"key": "allow_withdraw", "description": "Let the agent withdraw sources on request",
             "default": "true", "choices": ["true", "false"]},
        ]

    def save_config(self, values: dict[str, Any], hermes_home: str) -> None:
        merged = {**load_config(hermes_home), **{k: v for k, v in values.items() if k in DEFAULTS}}
        path = config_path(hermes_home)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config-")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(merged, handle, indent=2)
        os.replace(tmp, path)


def register(ctx) -> None:
    ctx.register_memory_provider(ProvenanceMemoryProvider())
