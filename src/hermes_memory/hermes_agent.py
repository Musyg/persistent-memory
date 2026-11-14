"""Memory provider for Nous Research's Hermes Agent, on the operations surface.

Hermes Agent finds it through the ``hermes_agent.memory_providers`` entry point; select it
with ``memory.provider: persistent-memory`` in the profile's config.yaml. It exposes the same
ten tools as the MCP server, recalls validated memory before each turn, and opens the turn
with a notice when something the session was shown is no longer valid. Admission stays
explicit: nothing from the conversation is stored unless a tool call asks for it.

Configuration lives in ``$HERMES_HOME/persistent-memory/config.json``. ``store_dir`` lets
Hermes Agent share one store with other clients (an MCP server, a script).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
from pathlib import Path

from .core import MemoryError
from .mcp_server import INSTRUCTIONS, TOOLS, Toolbox
from .persistent import PersistentMemory

try:  # pragma: no cover - depends on the environment
    from agent.memory_provider import MemoryProvider, RecallStatus, is_trivial_prompt
    from tools.registry import tool_error
    HERMES_AGENT_AVAILABLE = True
except ImportError:
    import re
    from dataclasses import dataclass

    HERMES_AGENT_AVAILABLE = False

    class MemoryProvider:
        """Stand-in base: Hermes Agent's ABC replaces it when Hermes Agent is installed."""

        pre_compress_checkpoint_api_version = 1

    @dataclass(frozen=True)
    class RecallStatus:
        provider_label: str
        count: int
        glyph: str = "*"

    _TRIVIAL = re.compile(r"^(yes|no|ok|okay|sure|thanks|thank you|hi|hello|hey|continue|go ahead|done|"
                          r"next|lgtm)[\s!?.,:;]*$", re.IGNORECASE)

    def is_trivial_prompt(text):
        stripped = (text or "").strip()
        return not stripped or stripped.startswith("/") or bool(_TRIVIAL.match(stripped))

    def tool_error(message, **extra):
        return json.dumps({"error": str(message)[:500], **extra}, ensure_ascii=False)

__all__ = ["PROVIDER_NAME", "PersistentMemoryProvider", "register", "load_config", "HERMES_AGENT_AVAILABLE"]

logger = logging.getLogger("persistent_memory.hermes_agent")

PROVIDER_NAME = "persistent-memory"
DEFAULTS = {"store_dir": "", "workspace": "hermes", "prefetch": True, "top_k": 5, "max_context_chars": 2000,
            "allow_withdraw": True, "qdrant_url": "", "qdrant_collection": "", "qdrant_min_score": 0.5,
            "embed_url": "", "embed_model": "", "embed_query_prefix": "", "embed_document_prefix": ""}


def config_path(hermes_home):
    return Path(hermes_home) / PROVIDER_NAME / "config.json"


def load_config(hermes_home):
    try:
        stored = json.loads(config_path(hermes_home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}


def _as_bool(value):
    return value if isinstance(value, bool) else str(value).strip().lower() in {"1", "true", "yes", "on"}


def _format_items(items):
    lines = ["## Persistent memory (validated for this turn)"]
    lines += ["- [%s] (%s) %s" % (i["artifact_id"], i["metadata"]["evidence_kind"], i["text"]) for i in items]
    lines.append("Cite the artifact_id in brackets when you use one of these.")
    return "\n".join(lines)


def _format_notices(notices):
    ids = sorted({n["artifact_id"] for n in notices})
    return ("## No longer valid\n"
            "These were shown earlier in this conversation and have since been withdrawn, invalidated "
            "or superseded: " + ", ".join("[%s]" % i for i in ids) + ". Do not rely on, repeat or build "
            "on them, including your own earlier answers. If they were superseded, search again.")


class _Projection:
    """Projection options read from the provider configuration, in the MCP server's shape."""

    def __init__(self, config):
        self.qdrant_url = config["qdrant_url"] or None
        self.qdrant_collection = config["qdrant_collection"] or None
        self.qdrant_api_key_env = "PERSISTENT_MEMORY_QDRANT_API_KEY"
        self.embed_url = config["embed_url"] or None
        self.embed_model = config["embed_model"] or None
        self.embed_api_key_env = "PERSISTENT_MEMORY_EMBED_API_KEY"
        self.embed_query_prefix = str(config["embed_query_prefix"])
        self.embed_document_prefix = str(config["embed_document_prefix"])
        self.qdrant_min_score = float(config["qdrant_min_score"])


class PersistentMemoryProvider(MemoryProvider):
    """One instance per Hermes profile; all state is bound in initialize()."""

    def __init__(self):
        self.memory = None
        self.toolbox = None
        self.config = dict(DEFAULTS)
        self.session_id = ""
        self.writes_allowed = True
        self._last_count = None

    @property
    def name(self):
        return PROVIDER_NAME

    def is_available(self):
        return True

    def unavailable_reason(self):
        return ""

    def initialize(self, session_id, **kwargs):
        from .mcp_server import attach_projection

        home = kwargs.get("hermes_home")
        if not home:
            raise RuntimeError("hermes_home is required")
        self.config = load_config(home)
        root = Path(os.path.expanduser(self.config["store_dir"])) if self.config["store_dir"] \
            else Path(home) / PROVIDER_NAME / "store"
        self.memory = PersistentMemory(root, str(self.config["workspace"]), create=True)
        try:
            attach_projection(self.memory, _Projection(self.config))
        except (MemoryError, OSError) as exc:
            logger.warning("vector projection not attached: %s", exc)
        self.writes_allowed = kwargs.get("agent_context", "primary") in (None, "primary")
        self.toolbox = Toolbox(self.memory, read_only=not self.writes_allowed,
                               allow_withdraw=_as_bool(self.config["allow_withdraw"]))
        self.session_id = session_id or ""

    def on_session_switch(self, new_session_id, *, parent_session_id="", reset=False, rewound=False, **kwargs):
        self.session_id = new_session_id or ""

    def _session(self, session_id=""):
        return "hermes:" + (session_id or self.session_id or "default")

    def system_prompt_block(self):
        return "# Persistent memory\n" + INSTRUCTIONS if self.memory is not None else ""

    def prefetch(self, query, *, session_id=""):
        if self.memory is None:
            return ""
        session = self._session(session_id)
        parts = []
        self._last_count = None
        try:
            notices = self.memory.notices(session)["notices"]
            if notices:
                parts.append(_format_notices(notices))
            if _as_bool(self.config["prefetch"]) and not is_trivial_prompt(query):
                result = self.memory.search(query[:4096], top_k=int(self.config["top_k"]),
                                            max_chars=int(self.config["max_context_chars"]), session=session)
                items = result["items"] if result["status"] == "completed" else []
                self._last_count = len(items)
                if items:
                    parts.append(_format_items(items))
        except (MemoryError, OSError, sqlite3.Error) as exc:
            logger.warning("prefetch failed: %s", exc)
        return "\n\n".join(parts)

    def recall_status(self):
        return RecallStatus("Persistent memory", self._last_count) if self._last_count else None

    def sync_turn(self, user_content, assistant_content, *, session_id="", messages=None, **kwargs):
        """Deliberately empty: admission is explicit, through the memory tools only."""

    def get_tool_schemas(self):
        # Hermes Agent builds its routing table when the provider is added, before initialize():
        # announce every tool then; after initialize() a disabled tool is left out and refused.
        tools = TOOLS if self.toolbox is None else self.toolbox.list()
        return [{"name": t["name"], "description": t["description"], "parameters": t["inputSchema"]}
                for t in tools]

    def handle_tool_call(self, tool_name, args, **kwargs):
        if self.toolbox is None:
            return tool_error("persistent memory is not initialized")
        if tool_name not in self.toolbox.names():
            return tool_error("unknown or disabled tool: %s" % tool_name)
        if not isinstance(args, dict):
            return tool_error("arguments must be an object")
        payload, is_error = self.toolbox.call(tool_name, args, self._session())
        if is_error:
            return tool_error(payload.get("error", "refused"),
                              **{k: v for k, v in payload.items() if k != "error"})
        return json.dumps(payload, ensure_ascii=False)

    def get_config_schema(self):
        return [
            {"key": "store_dir", "description": "Store directory; empty = inside this profile. Point it at "
                                                "the store your MCP clients use to share one memory."},
            {"key": "workspace", "description": "Memory workspace for this profile", "default": "hermes"},
            {"key": "prefetch", "description": "Recall validated memory before each turn",
             "default": "true", "choices": ["true", "false"]},
            {"key": "max_context_chars", "description": "Character budget for recalled memory",
             "type": "integer", "default": 2000, "minimum": 200, "maximum": 16000},
            {"key": "allow_withdraw", "description": "Let the agent withdraw artifacts on request",
             "default": "true", "choices": ["true", "false"]},
            {"key": "qdrant_url", "description": "Optional Qdrant URL for semantic recall"},
            {"key": "embed_url", "description": "OpenAI-compatible embeddings base URL (with qdrant_url)"},
            {"key": "embed_model", "description": "Embedding model name (with qdrant_url)"},
        ]

    def save_config(self, values, hermes_home):
        merged = {**load_config(hermes_home), **{k: v for k, v in values.items() if k in DEFAULTS}}
        path = config_path(hermes_home)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config-")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(merged, handle, indent=2)
        os.replace(tmp, path)


def register(ctx):
    ctx.register_memory_provider(PersistentMemoryProvider())
