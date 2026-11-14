"""MCP tools over the provenance store shared with the Hermes Agent provider.

Exposure is recorded per MCP session: when a source shown in a session is withdrawn,
the next tool result of that session carries a ``withdrawn_notice``, once per source.
"""

from __future__ import annotations

import json
from typing import Any

from hermes_agent_provenance.store import Store
from hermes_memory.typed_memory import KINDS

KIND_CHOICES = sorted(KINDS)
MAX_TEXT_BYTES = 512000

NOTICE = ("These sources were shown earlier in this session and have been withdrawn since. Do not rely on, "
          "repeat or build on anything that came from them, including your own earlier answers.")


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str], *,
          read_only: bool, destructive: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": properties, "required": required,
                        "additionalProperties": False},
        "annotations": {"readOnlyHint": read_only, "destructiveHint": destructive,
                        "idempotentHint": read_only, "openWorldHint": False},
    }


SEARCH = _tool(
    "provenance_search",
    "Search long-term memory. Every result is checked against current authority at read time; withdrawn or "
    "superseded sources are never returned. Cite the source_id of any result you rely on.",
    {"query": {"type": "string", "minLength": 1, "maxLength": 4096},
     "kinds": {"type": "array", "items": {"type": "string", "enum": KIND_CHOICES}},
     "top_k": {"type": "integer", "minimum": 1, "maximum": 20}},
    ["query"], read_only=True)
EXPLAIN = _tool(
    "provenance_explain",
    "Explain a source: its versions, whether it is readable now, and what depends on it. Metadata only.",
    {"source_id": {"type": "string", "minLength": 1, "maxLength": 512}},
    ["source_id"], read_only=True)
REMEMBER = _tool(
    "provenance_remember",
    "Store one durable fact, decision or procedure the user stated or confirmed. Use kind 'hypothesis' for "
    "guesses. Returns the new source_id.",
    {"text": {"type": "string", "minLength": 1},
     "kind": {"type": "string", "enum": KIND_CHOICES},
     "aliases": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 512}, "maxItems": 32}},
    ["text"], read_only=False)
WITHDRAW = _tool(
    "provenance_withdraw",
    "Withdraw a stored source when the user says it is wrong, outdated or must be forgotten. Everything "
    "derived from it stops being readable. Not physical erasure.",
    {"source_id": {"type": "string", "minLength": 1, "maxLength": 512},
     "reason": {"type": "string", "maxLength": 500}},
    ["source_id", "reason"], read_only=False, destructive=True)


class ToolError(ValueError):
    """Invalid arguments or an unknown source: reported as a tool result with isError."""


def _str(args: dict[str, Any], key: str, *, required: bool = True, limit: int = 4096) -> str:
    value = args.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise ToolError(f"invalid_{key}")
    return value


class Tools:
    def __init__(self, store: Store, *, allow_write: bool = True, allow_withdraw: bool = True,
                 max_context_chars: int = 4000) -> None:
        self.store = store
        self.allow_write = allow_write
        self.allow_withdraw = allow_write and allow_withdraw
        self.max_context_chars = max_context_chars

    def list(self) -> list[dict[str, Any]]:
        tools = [SEARCH, EXPLAIN]
        if self.allow_write:
            tools.append(REMEMBER)
        if self.allow_withdraw:
            tools.append(WITHDRAW)
        return tools

    def names(self) -> set[str]:
        return {t["name"] for t in self.list()}

    def call(self, name: str, args: dict[str, Any], exposure_session: str) -> tuple[dict[str, Any], bool]:
        """Run one tool. Returns (payload, is_error). Unknown names must be filtered by the caller."""
        withdrawn = self.store.withdrawn_since_shown(exposure_session)
        if withdrawn:
            self.store.mark_notified(exposure_session, [d["ref"] for d in withdrawn])
        try:
            if set(args) - set(next(t for t in self.list() if t["name"] == name)["inputSchema"]["properties"]):
                raise ToolError("unknown_argument")
            payload, is_error = self._run(name, args, exposure_session), False
        except ToolError as exc:
            payload, is_error = {"error": str(exc)}, True
        except LookupError as exc:
            payload, is_error = {"error": str(exc)}, True
        if withdrawn:
            payload["withdrawn_notice"] = {
                "withdrawn_source_ids": sorted({d["ref"]["artifact_id"] for d in withdrawn}),
                "instruction": NOTICE,
            }
        return payload, is_error

    def _run(self, name: str, args: dict[str, Any], session: str) -> dict[str, Any]:
        if name == "provenance_search":
            query = _str(args, "query")
            kinds = args.get("kinds")
            if kinds is not None and (not isinstance(kinds, list) or not all(k in KINDS for k in kinds)):
                raise ToolError("invalid_kinds")
            top_k = args.get("top_k", 5)
            if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 20:
                raise ToolError("invalid_top_k")
            result = self.store.search(query, kinds=kinds or None, top_k=top_k, max_chars=self.max_context_chars)
            items = result.get("items", []) if result.get("status") == "completed" else []
            self.store.record_exposure(session, [i["ref"] for i in items], "mcp")
            return {"status": result.get("status"), "results": [
                {"source_id": i["ref"]["artifact_id"], "version_id": i["ref"]["version_id"],
                 "kind": i["metadata"]["evidence_kind"], "text": i["text"]} for i in items]}
        if name == "provenance_explain":
            return self.store.explain(_str(args, "source_id", limit=512))
        if name == "provenance_remember":
            text = _str(args, "text", limit=MAX_TEXT_BYTES)
            if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
                raise ToolError("invalid_text")
            kind = args.get("kind", "observation")
            if kind not in KINDS:
                raise ToolError("invalid_kind")
            aliases = args.get("aliases")
            if aliases is not None and (not isinstance(aliases, list) or len(aliases) > 32
                                        or not all(isinstance(a, str) and 0 < len(a) <= 512 for a in aliases)):
                raise ToolError("invalid_aliases")
            try:
                return self.store.remember(text.strip(), kind, aliases or None)
            except ValueError as exc:
                raise ToolError(str(exc)) from exc
        if name == "provenance_withdraw":
            source_id = _str(args, "source_id", limit=512)
            reason = _str(args, "reason", required=False, limit=500)
            return self.store.withdraw(source_id, reason, session)
        raise ToolError("unknown_tool")


def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
