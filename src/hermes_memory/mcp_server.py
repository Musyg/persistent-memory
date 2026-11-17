"""MCP server for the operations surface, Python standard library only.

    persistent-memory-mcp --store ~/.persistent-memory --create
    persistent-memory-mcp --store ~/.persistent-memory --transport http --port 8766

Over stdio, one process serves one client with newline-delimited JSON-RPC; logs go to
stderr, and the process is one ledger session. Over HTTP (mcp_http), each MCP session is
one ledger session. Every tool goes through PersistentMemory, so an MCP client gets the
same memory as any other integration: exact versions, derived artifacts, corrections,
withdrawal with cascade, lessons and withdrawal notices. When a version a session was
shown stops being valid, its next tool result carries a notice, once.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import uuid

from . import __version__
from .core import MemoryError
from .persistent import KINDS, RELATIONS, PersistentMemory
from .typed_memory import RetrievalError

__all__ = ["SUPPORTED_VERSIONS", "Toolbox", "Session", "serve", "main"]

logger = logging.getLogger("persistent_memory.mcp")

SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
STRUCTURED_SINCE = "2025-06-18"
MAX_MESSAGE_BYTES = 4 * 1024 * 1024
INSTRUCTIONS = (
    "Long-term memory with provenance. Search it before answering about earlier facts, decisions "
    "or procedures, and cite the artifact_id of what you rely on. Store something only when the "
    "user states or confirms it; use kind 'hypothesis' for guesses. When a correction or a "
    "withdrawal is asked for, use memory_correct or memory_withdraw rather than storing a "
    "contradicting fact. If a result carries memory_notices, stop relying on those artifacts, "
    "including what you said from them earlier."
)
REVIEW_INSTRUCTIONS = (
    " In this server, storing, deriving, correcting, withdrawing and learning create proposals that a "
    "person approves; nothing changes until then. Tell the user a proposal is waiting for approval, do "
    "not send it again, and use memory_proposal_status to see where it stands."
)

_STR = {"type": "string"}
_ID = {"type": "string", "description": "The artifact_id returned when it was stored or found by memory_search."}
_REF = {"type": "object", "additionalProperties": False,
        "required": ["workspace", "artifact_id", "version_id"],
        "properties": {"workspace": _STR, "artifact_id": _STR, "version_id": _STR},
        "description": "An exact version: the ref object returned by memory_search, memory_remember or "
                       "memory_derive, copied unchanged."}
_KIND = {"type": "string", "enum": sorted(KINDS),
         "description": "observation for a fact, document for a text, procedure for how to do something, "
                        "task, feedback, or hypothesis for a guess nobody confirmed."}
_PARENT = {"description": "An exact parent version (a ref), or {ref, relation}. derives (the default) and "
                          "indexes make this artifact unreadable when the parent changes; cites does not.",
           "anyOf": [_REF, {"type": "object", "additionalProperties": False, "required": ["ref", "relation"],
                            "properties": {"ref": _REF, "relation": {"type": "string", "enum": list(RELATIONS)}}}]}
_META = {
    "aliases": {"type": "array", "items": _STR, "maxItems": 32, "description": "Short names to find it again."},
    "valid_from": {"type": "string", "description": "UTC time it starts to apply, e.g. 2026-01-31T00:00:00Z. Leave out unless the user gave one; by default it applies now."},
    "valid_until": {"type": "string", "description": "UTC time after which it no longer applies. Leave out unless the user gave one."},
    "preconditions": {"type": "object", "description": "Exact conditions a search must supply to see it. Leave out unless the user said it only holds under a condition: a search without these conditions will not return it."},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1, "description": "Declared, not computed. Leave out unless the user gave one."},
}
_RAW = {"anyOf": [_STR, {"type": "object"}]}


def _tool(name, title, description, properties, required=(), read_only=False, destructive=False,
          idempotent=False):
    return {"name": name, "title": title, "description": description,
            "inputSchema": {"type": "object", "properties": properties, "required": list(required),
                            "additionalProperties": False},
            "annotations": {"title": title, "readOnlyHint": read_only, "destructiveHint": destructive,
                            "idempotentHint": idempotent, "openWorldHint": False}}


TOOLS = (
    _tool("memory_search", "Search memory",
          "Find stored facts, decisions and procedures by keywords. Use it before answering about anything "
          "the user said or decided earlier. Returns only current, valid versions, each with its text, kind, "
          "artifact_id and exact ref; withdrawn, superseded and expired versions are left out, and an empty "
          "list means nothing valid matches. Read-only. To re-read one version you already hold, use "
          "memory_read.",
          {"query": {"type": "string", "description": "Keywords or a question."},
           "kinds": {"type": "array", "items": _KIND, "description": "Only these kinds. Leave out to search all."},
           "conditions": {"type": "object", "description": "Facts about the current situation, matched "
                                                           "exactly against stored preconditions. Leave out "
                                                           "unless the user describes a situation."},
           "as_of": {"type": "string", "description": "UTC time to check validity at. Leave out for now."},
           "top_k": {"type": "integer", "minimum": 1, "maximum": 20,
                     "description": "Maximum number of results, default 5. Leave out unless you need more."},
           "max_chars": {"type": "integer", "minimum": 200, "maximum": 16000,
                         "description": "Maximum characters of text returned in total, default 2000."}},
          ["query"], read_only=True, idempotent=True),
    _tool("memory_read", "Read one version",
          "Re-read one exact version you got from memory_search or a write, for example before relying on it "
          "again later in a conversation. Returns its text if it is still valid; otherwise allowed is false "
          "and reason and state say why (superseded, withdrawn, expired), with no text. Read-only. To look "
          "for something, use memory_search.",
          {"ref": _REF}, ["ref"], read_only=True, idempotent=True),
    _tool("memory_remember", "Remember a source",
          "Store a new fact, decision, document or procedure the user stated or confirmed, as a source. Do "
          "not use it for your own conclusions (memory_derive), for lessons after a task (memory_learn), or "
          "to change something already stored (memory_correct). Returns artifact_id and ref. Sending the same "
          "source_id with the same text again changes nothing; with a different text it is refused with "
          "version_conflict.",
          {"text": {"type": "string", "description": "Self-contained statement, with its date if known."},
           "kind": _KIND,
           "source_id": {"type": "string", "description": "Stable name you choose, such as 'db-port', to "
                                                          "correct or withdraw it later. Leave out to get one."},
           **_META}, ["text"]),
    _tool("memory_derive", "Derive from exact parents",
          "Store a summary, conclusion or procedure you built from entries already in memory, linked to the "
          "exact versions it came from. Use it instead of memory_remember whenever the text depends on stored "
          "entries: if one of them is later corrected or withdrawn, this artifact stops being served and "
          "sessions that saw it are notified. Returns artifact_id and ref.",
          {"text": {"type": "string", "description": "The derived statement, self-contained."},
           "parents": {"type": "array", "items": _PARENT, "minItems": 1, "maxItems": 64,
                       "description": "The refs it was built from, as returned by memory_search."},
           "kind": _KIND,
           "artifact_id": {"type": "string", "description": "Stable name you choose. Leave out to get one."},
           **_META}, ["text", "parents"]),
    _tool("memory_correct", "Correct an artifact",
          "Replace an artifact's text when the user corrects it, keeping its history. Only applies if "
          "expected_version is still its current version; otherwise it is refused with version_conflict, and "
          "you search again. Metadata you leave out is kept. Whatever was derived from the old version stops "
          "being served and its readers are notified. To remove something entirely, use memory_withdraw.",
          {"artifact_id": _ID, "text": {"type": "string", "description": "The corrected statement."},
           "expected_version": {"type": "string", "description": "The version_id of the ref you read."},
           "parents": {"type": "array", "items": _PARENT, "minItems": 1, "maxItems": 64,
                       "description": "For a derived artifact: its new parents. Leave out to keep them."},
           **_META},
          ["artifact_id", "text", "expected_version"]),
    _tool("memory_explain", "Explain an artifact",
          "Explain why an artifact is or is not served: its state, its versions, what it was derived from and "
          "what depends on it. Metadata only, never text. Use it when a search leaves out something the user "
          "expects, or before a correction. Read-only; unknown_artifact if it does not exist. Give "
          "artifact_id or ref.",
          {"artifact_id": _ID, "ref": _REF}, read_only=True, idempotent=True),
    _tool("memory_plan_withdrawal", "Plan a withdrawal",
          "Preview a withdrawal: list every version that memory_withdraw would stop serving, the artifact and "
          "everything derived from it, without changing anything. Use it to show the user the consequences "
          "before withdrawing.",
          {"artifact_id": _ID}, ["artifact_id"], read_only=True, idempotent=True),
    _tool("memory_withdraw", "Withdraw an artifact",
          "Stop serving an artifact the user says is wrong, outdated or must be forgotten, together with "
          "everything derived from it; sessions that saw them are notified. The text is not physically erased "
          "and the history keeps the reason. Run memory_plan_withdrawal first when the user should see what "
          "it blocks. To replace a text with a better one, use memory_correct instead.",
          {"artifact_id": _ID,
           "reason": {"type": "string", "maxLength": 500, "description": "Why, in the user's words."},
           "event_id": {"type": "string", "description": "Optional key; repeating a call with the same key "
                                                         "changes nothing."}},
          ["artifact_id", "reason"], destructive=True, idempotent=True),
    _tool("memory_learn", "Learn a lesson",
          "After a task, store the lesson drawn from it, with the task trace and the feedback it got kept as "
          "its provenance. Only the lesson is returned by searches; withdrawing the trace or the feedback "
          "stops serving the lesson. For a fact the user states, use memory_remember.",
          {"trace": {**_RAW, "description": "What was done: steps, commands or a summary of them."},
           "feedback": {**_RAW, "description": "What the user or a check said about the result."},
           "lesson": {"type": "string", "description": "The rule to apply next time, self-contained."},
           "kind": _KIND,
           "lesson_id": {"type": "string", "description": "Stable name you choose. Leave out to get one."},
           "aliases": _META["aliases"], "preconditions": _META["preconditions"],
           "valid_from": _META["valid_from"], "valid_until": _META["valid_until"],
           "confidence": _META["confidence"]},
          ["trace", "feedback", "lesson"]),
    _tool("memory_notices", "Check notices",
          "List the artifacts this session was shown that have since been withdrawn, invalidated or "
          "superseded, so you stop relying on them and on what you said from them. Each is reported once. "
          "Other tool results already carry new notices as memory_notices; call this when you need to check "
          "explicitly, for example before a final answer.",
          {}, read_only=True),
)
PROPOSAL_STATUS = _tool(
    "memory_proposal_status", "Check proposals",
    "Review mode only: see whether proposals you made are pending, approved, rejected or failed, with the "
    "result once approved or the refusal code once failed. Give proposal_id for one proposal of this "
    "workspace; leave it out for the latest ones of this session. Read-only: a person approves, never this "
    "server.",
    {"proposal_id": {"type": "string", "description": "As returned when the proposal was made."}},
    read_only=True, idempotent=True)
_REVIEW_PREFIX = "Review mode: this call creates a proposal that a person must approve; nothing is stored until then. "
READ_ONLY = frozenset({"memory_search", "memory_read", "memory_explain", "memory_plan_withdrawal",
                       "memory_notices"})
_JSON_TYPES = {"string": str, "integer": int, "number": (int, float), "array": list, "object": dict,
               "boolean": bool}


def _matches(schema, value):
    if "anyOf" in schema:
        return any(_matches(option, value) for option in schema["anyOf"])
    expected = _JSON_TYPES.get(schema.get("type"))
    if expected is None:
        return True
    if type(value) is bool and schema["type"] != "boolean":
        return False
    return isinstance(value, expected)


class Toolbox:
    """The tools of one store and workspace, independent of the transport."""

    def __init__(self, memory, *, read_only=False, allow_withdraw=True, review=False):
        if read_only and review:
            raise ValueError("read_only_and_review_are_exclusive")
        self.memory = memory
        names = {t["name"] for t in TOOLS}
        if read_only:
            names &= READ_ONLY
        if not allow_withdraw:
            names.discard("memory_withdraw")
        self._tools = [t for t in TOOLS if t["name"] in names]
        self.proposals = None
        self.instructions = INSTRUCTIONS
        if review:
            from .review import Proposals, WRITE_TOOLS
            self.proposals = Proposals(memory.root)
            self.instructions = INSTRUCTIONS + REVIEW_INSTRUCTIONS
            self._tools = [dict(t, description=_REVIEW_PREFIX + t["description"]) if t["name"] in WRITE_TOOLS
                           else t for t in self._tools] + [PROPOSAL_STATUS]
        self._schemas = {t["name"]: t["inputSchema"] for t in self._tools}

    def list(self):
        return [dict(t) for t in self._tools]

    def names(self):
        return frozenset(self._schemas)

    def _check(self, name, args):
        schema = self._schemas[name]
        for key in args:
            if key not in schema["properties"]:
                raise MemoryError("unknown_argument:" + key)
        for key in schema["required"]:
            if key not in args:
                raise MemoryError("missing_argument:" + key)
        for key, value in args.items():
            prop = schema["properties"][key]
            if not _matches(prop, value):
                raise MemoryError("invalid_argument:" + key)
            if prop.get("type") in ("integer", "number") and not (
                    prop.get("minimum", value) <= value <= prop.get("maximum", value)):
                raise MemoryError("invalid_argument:" + key)

    def _absent_nulls(self, name, args):
        """An optional argument sent as null, or empty ("", [] or {}), means absent: some framework adapters
        send every unset field, and some models fill unused fields with empty values. An empty kinds filter
        would otherwise exclude every result. Unknown arguments and required ones stay checked as before."""
        schema = self._schemas.get(name)
        if schema is None or not isinstance(args, dict):
            return args
        required = set(schema["required"])
        properties = schema["properties"]

        def absent(key, value):
            if key not in properties or key in required:
                return False
            if value is None:
                return True
            empty = {"string": "", "array": [], "object": {}}.get(properties[key].get("type"), None)
            return empty is not None and type(value) is type(empty) and value == empty

        return {key: value for key, value in args.items() if not absent(key, value)}

    def _hint(self, name, code):
        """What a model needs to correct a refused call, next to the unchanged error code."""
        schema = self._schemas.get(name)
        properties = schema["properties"] if schema else {}
        if code in ("invalid_evidence_kind", "invalid_kind_filter"):
            return {"allowed_kinds": sorted(KINDS)}
        if code == "utc_timestamp_required":
            return {"hint": "Times are UTC in ISO 8601 ending in Z, for example 2026-01-31T00:00:00Z. "
                            "Leave out an optional time you do not need."}
        if code.startswith("unknown_argument:"):
            return {"allowed_arguments": sorted(properties)}
        if code.startswith(("invalid_argument:", "missing_argument:")):
            key = code.split(":", 1)[1]
            prop = properties.get(key, {})
            hint = {"expected_type": prop["type"]} if "type" in prop else {}
            hint.update({bound: prop[bound] for bound in ("minimum", "maximum") if bound in prop})
            return hint
        if code == "version_conflict":
            return {"hint": "Search again and use the version_id of the current ref as expected_version, "
                            "or use memory_correct to change an existing artifact."}
        return {}

    def call(self, name, args, session):
        """Return (payload, is_error). Refusals become tool errors the model can read."""
        try:
            args = self._absent_nulls(name, args)
            self._check(name, args)
            payload = self._run(name, dict(args), session)
            is_error = False
        except (MemoryError, ValueError, TypeError) as exc:
            code = str(exc) or type(exc).__name__
            payload, is_error = {"error": code, **self._hint(name, code)}, True
        except (OSError, sqlite3.Error):
            logger.exception("tool %s failed", name)
            payload, is_error = {"error": "memory_unavailable"}, True
        if name != "memory_notices":
            try:
                notices = self.memory.notices(session)["notices"]
            except (OSError, sqlite3.Error, ValueError):
                logger.exception("notice check failed")
                notices = []
            if notices:
                payload = {**payload, "memory_notices": notices}
        return payload, is_error

    def _run(self, name, args, session):
        m = self.memory
        if self.proposals is not None:
            from .review import WRITE_TOOLS
            if name in WRITE_TOOLS:
                proposal_id = self.proposals.propose(m.workspace, name, args, session)
                return {"status": "pending_review", "proposal_id": proposal_id,
                        "hint": "Nothing is stored until a person approves it. memory_proposal_status "
                                "shows where it stands."}
            if name == "memory_proposal_status":
                if "proposal_id" in args:
                    return self._status_view(self.proposals.get(args["proposal_id"], m.workspace))
                return {"proposals": [self._status_view(p) for p in self.proposals.list(
                    workspace=m.workspace, session_id=session, states=None, limit=20)]}
        if name == "memory_search":
            out = m.search(args.pop("query"), session=session, **args)
            reasons = {}
            for item in out["exclusions"]:
                reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
            result = {"status": out["status"], "complete": out["complete"], "items": [
                {"artifact_id": i["artifact_id"], "ref": i["ref"], "kind": i["metadata"]["evidence_kind"],
                 "text": i["text"], "metadata": i["metadata"]} for i in out["items"]],
                "excluded": reasons}
            if "semantic" in out:
                result["semantic"] = out["semantic"]
            return result
        if name == "memory_read":
            return m.read(args["ref"], session=session)
        if name == "memory_remember":
            return m.remember(args.pop("text"), **args)
        if name == "memory_derive":
            return m.derive(args.pop("text"), **args)
        if name == "memory_correct":
            return m.correct(args.pop("artifact_id"), args.pop("text"), **args)
        if name == "memory_explain":
            if ("artifact_id" in args) == ("ref" in args):
                raise MemoryError("give_artifact_id_or_ref")
            return m.explain(args.get("artifact_id", args.get("ref")))
        if name == "memory_plan_withdrawal":
            return m.plan_withdrawal(args["artifact_id"])
        if name == "memory_withdraw":
            return m.withdraw(args["artifact_id"], args["reason"], event_id=args.get("event_id"),
                              session=session)
        if name == "memory_learn":
            return m.learn(args.pop("trace"), args.pop("feedback"), args.pop("lesson"), **args)
        if name == "memory_notices":
            return m.notices(session)
        raise MemoryError("unknown_tool")


    @staticmethod
    def _status_view(proposal):
        return {key: proposal[key] for key in ("proposal_id", "tool", "state", "created_at", "decided_at",
                                               "result", "error", "note") if key in proposal}


def _error(ident, code, message):
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}}


class Session:
    """JSON-RPC state of one MCP connection."""

    def __init__(self, toolbox, session_id):
        self.toolbox = toolbox
        self.session_id = session_id
        self.protocol = None
        self.ready = False

    def handle(self, message):
        """One decoded message in, one response dict out (None for notifications)."""
        if isinstance(message, list):
            return _error(None, -32600, "Batching is not supported")
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(None, -32600, "Invalid Request")
        if "method" not in message:
            return None  # a response from the client; this server sends no requests
        method, ident, params = message["method"], message.get("id"), message.get("params", {})
        if not isinstance(method, str) or not isinstance(params, dict):
            return _error(ident, -32600, "Invalid Request")
        if "id" not in message:
            if method == "notifications/initialized" and self.protocol is not None:
                self.ready = True
            return None
        if method == "initialize":
            return self._initialize(ident, params)
        if method == "ping":
            return {"jsonrpc": "2.0", "id": ident, "result": {}}
        if method == "server/discover":
            return _error(ident, -32601, "Method not found")
        if self.protocol is None or not self.ready:
            return _error(ident, -32002, "Initialization not completed")
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": ident, "result": {"tools": self.toolbox.list()}}
        if method == "tools/call":
            name, args = params.get("name"), params.get("arguments", {})
            if name not in self.toolbox.names() or not isinstance(args, dict):
                return _error(ident, -32602, "Unknown tool or invalid arguments")
            payload, is_error = self.toolbox.call(name, args, self.session_id)
            result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                      "isError": is_error}
            if self.protocol >= STRUCTURED_SINCE:
                result["structuredContent"] = payload
            return {"jsonrpc": "2.0", "id": ident, "result": result}
        return _error(ident, -32601, "Method not found")

    def _initialize(self, ident, params):
        if self.protocol is not None:
            return _error(ident, -32600, "Already initialized")
        requested = params.get("protocolVersion")
        if not isinstance(requested, str) or not isinstance(params.get("capabilities"), dict) \
                or not isinstance(params.get("clientInfo"), dict):
            return _error(ident, -32602, "Invalid initialize params")
        self.protocol = requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
        return {"jsonrpc": "2.0", "id": ident, "result": {
            "protocolVersion": self.protocol, "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "persistent-memory", "title": "Persistent Memory", "version": __version__},
            "instructions": getattr(self.toolbox, "instructions", INSTRUCTIONS)}}


def serve(session, stdin, stdout):
    """Serve newline-delimited JSON-RPC until stdin closes. stdin and stdout are binary."""
    while True:
        line = stdin.readline(MAX_MESSAGE_BYTES + 1)
        if not line:
            return 0
        if len(line) > MAX_MESSAGE_BYTES:
            if not line.endswith(b"\n"):
                while True:
                    rest = stdin.readline(MAX_MESSAGE_BYTES)
                    if not rest or rest.endswith(b"\n"):
                        break
            response = _error(None, -32600, "Message too large")
        elif not line.strip():
            continue
        else:
            try:
                message = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                response = _error(None, -32700, "Parse error")
            else:
                response = session.handle(message)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")
            stdout.flush()


def add_projection_options(parser):
    group = parser.add_argument_group("vector projection (optional)")
    group.add_argument("--semantic", action="store_true",
                       default=os.environ.get("PERSISTENT_MEMORY_SEMANTIC", "").strip().lower() in ("1", "true", "yes", "on"),
                       help="Also search by meaning, with vectors kept in the store folder (vectors.db). "
                            "Uses --embed-url when given, otherwise a model run in the process "
                            '(pip install "persistent-memory-mcp[semantic]")')
    group.add_argument("--semantic-min-score", type=float, default=None,
                       help="With --semantic: cosine score below which a candidate is ignored; default 0.3 "
                            "for the default model, 0.5 otherwise; tune per model")
    group.add_argument("--qdrant-url", default=os.environ.get("PERSISTENT_MEMORY_QDRANT_URL"),
                       help="Qdrant URL, e.g. http://127.0.0.1:6333")
    group.add_argument("--qdrant-collection", help="Collection name; default derived from workspace and model")
    group.add_argument("--qdrant-api-key-env", help="Environment variable holding the Qdrant API key")
    group.add_argument("--embed-url", default=os.environ.get("PERSISTENT_MEMORY_EMBED_URL"),
                       help="OpenAI-compatible base URL serving /embeddings, e.g. http://127.0.0.1:8000/v1")
    group.add_argument("--embed-model", default=os.environ.get("PERSISTENT_MEMORY_EMBED_MODEL"),
                       help="Embedding model name; with --semantic and no --embed-url, default "
                            "sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
    group.add_argument("--embed-api-key-env", help="Environment variable holding the embeddings API key")
    group.add_argument("--embed-query-prefix", default="", help='Text put before queries, e.g. "search_query: "')
    group.add_argument("--embed-document-prefix", default="", help='Text put before entries, e.g. "search_document: "')
    group.add_argument("--qdrant-min-score", type=float, default=0.5,
                       help="Cosine score below which a vector candidate is ignored; tune per model")


def attach_projection(memory, options):
    """Attach the vector projection the options ask for (Qdrant or local); return its status or None."""
    if getattr(options, "semantic", False):
        if options.qdrant_url:
            raise MemoryError("choose_semantic_or_qdrant")
        from .local_vectors import DEFAULT_MIN_SCORE, DEFAULT_MODEL, FastEmbedEmbeddings, LocalVectorProjection
        min_score = getattr(options, "semantic_min_score", None)
        if min_score is None:
            default = not options.embed_url and options.embed_model in (None, DEFAULT_MODEL)
            min_score = DEFAULT_MIN_SCORE if default else 0.5
        if options.embed_url:
            from .qdrant_projection import OpenAIEmbeddings
            if not options.embed_model:
                raise MemoryError("embed_url_needs_embed_model")
            embed = OpenAIEmbeddings(options.embed_url, options.embed_model, api_key_env=options.embed_api_key_env)
        else:
            embed = FastEmbedEmbeddings(options.embed_model or DEFAULT_MODEL, cache_dir=memory.root / "models")
        return memory.attach_projection(LocalVectorProjection(
            memory, embed, min_score=min_score,
            query_prefix=options.embed_query_prefix, document_prefix=options.embed_document_prefix))
    if not options.qdrant_url:
        return None
    from .qdrant_projection import OpenAIEmbeddings, QdrantProjection
    if not (options.embed_url and options.embed_model):
        raise MemoryError("qdrant_needs_embed_url_and_embed_model")
    embed = OpenAIEmbeddings(options.embed_url, options.embed_model, api_key_env=options.embed_api_key_env)
    return memory.attach_projection(QdrantProjection(memory, options.qdrant_url, embed,
                                                     collection=options.qdrant_collection,
                                                     api_key_env=options.qdrant_api_key_env,
                                                     min_score=options.qdrant_min_score,
                                                     query_prefix=options.embed_query_prefix,
                                                     document_prefix=options.embed_document_prefix))


STARTUP_ERRORS = (MemoryError, RetrievalError, sqlite3.Error, OSError)


def start_message(exc, store=None):
    """One line for a startup failure: the reason, plus how to recover when we know how."""
    text = " ".join(str(exc).split()) or exc.__class__.__name__
    if not isinstance(exc, MemoryError) and not str(exc):
        text = exc.__class__.__name__
    if text == "store_missing":
        return text + " (add --create to make a new one)"
    if text == "store_incomplete":
        return (text + " (creation was interrupted: authority exists but content.db is missing or empty; "
                "if the store holds no data, delete the store folder " + str(store or "") +
                " and start again with --create, otherwise restore content.db from a backup)")
    if isinstance(exc, (sqlite3.Error, OSError)):
        return exc.__class__.__name__ + ": " + text
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(prog="persistent-memory-mcp", description=__doc__.splitlines()[0])
    parser.add_argument("--store", default=None,
                        help="Store directory; default $PERSISTENT_MEMORY_DIR, else the platform data folder "
                             "(see persistent-memory status)")
    parser.add_argument("--workspace", default=os.environ.get("PERSISTENT_MEMORY_WORKSPACE", "default"))
    parser.add_argument("--create", action="store_true", help="Create the store if it does not exist")
    parser.add_argument("--read-only", action="store_true",
                        help="Expose search, read, explain, plan_withdrawal and notices only")
    parser.add_argument("--no-withdraw", action="store_true", help="Do not expose memory_withdraw")
    parser.add_argument("--review", action="store_true",
                        help="Writes become proposals that a person approves with persistent-memory review")
    parser.add_argument("--session", help="Ledger session id for stdio; default one new id per process")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP only")
    parser.add_argument("--port", type=int, default=8766, help="HTTP only")
    parser.add_argument("--token-file", help="HTTP only: bearer token file (owner-only); required off loopback")
    parser.add_argument("--allow-origin", action="append", default=[],
                        help="HTTP only: browser Origin allowed to call the endpoint; repeatable")
    add_projection_options(parser)
    args = parser.parse_args(argv)
    if args.read_only and args.review:
        parser.error("--read-only and --review cannot be combined: --read-only already exposes no writes")
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="persistent-memory-mcp: %(message)s")
    if not args.store:
        from .client_setup import default_store
        args.store = str(default_store())
    try:
        memory = PersistentMemory(os.path.expanduser(args.store), args.workspace, create=args.create)
        status = attach_projection(memory, args)
    except STARTUP_ERRORS as exc:
        print("persistent-memory-mcp: cannot start: " + start_message(exc, args.store), file=sys.stderr)
        return 2
    if status not in (None, "ok"):
        print("persistent-memory-mcp: vector projection " + status + "; lexical search still works",
              file=sys.stderr)
    try:
        toolbox = Toolbox(memory, read_only=args.read_only, allow_withdraw=not args.no_withdraw,
                          review=args.review)
    except STARTUP_ERRORS as exc:
        print("persistent-memory-mcp: cannot start: " + start_message(exc, args.store), file=sys.stderr)
        return 2
    if args.transport == "http":
        from .mcp_http import load_token, make_server
        try:
            token = load_token(args.token_file) if args.token_file else None
            server = make_server(toolbox, args.host, args.port, token, tuple(args.allow_origin))
        except (OSError, ValueError) as exc:
            print("persistent-memory-mcp: cannot start HTTP: " + str(exc), file=sys.stderr)
            return 2
        print("persistent-memory-mcp: serving http://%s:%d/mcp" % server.server_address[:2], file=sys.stderr)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    session = Session(toolbox, args.session or "mcp-" + uuid.uuid4().hex)
    try:
        return serve(session, sys.stdin.buffer, sys.stdout.buffer)
    except (BrokenPipeError, KeyboardInterrupt):
        return 0


if __name__ == "__main__":
    sys.exit(main())
