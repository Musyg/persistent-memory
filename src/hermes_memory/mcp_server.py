"""MCP server over stdio for the operations surface, Python standard library only.

    persistent-memory-mcp --store ~/.persistent-memory --create

One process serves one client over newline-delimited JSON-RPC on stdin and stdout; logs go
to stderr. Every tool goes through PersistentMemory, so an MCP client gets the same memory
as any other integration: exact versions, derived artifacts, corrections, withdrawal with
cascade, lessons and withdrawal notices. The process is one ledger session: when a version
it was shown stops being valid, the next tool result carries a notice, once.
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

_STR = {"type": "string"}
_REF = {"type": "object", "additionalProperties": False,
        "required": ["workspace", "artifact_id", "version_id"],
        "properties": {"workspace": _STR, "artifact_id": _STR, "version_id": _STR},
        "description": "An exact version, as returned by other tools."}
_KIND = {"type": "string", "enum": sorted(KINDS)}
_PARENT = {"description": "An exact parent version, or {ref, relation}. derives and indexes carry "
                          "invalidation to the child; cites does not.",
           "anyOf": [_REF, {"type": "object", "additionalProperties": False, "required": ["ref", "relation"],
                            "properties": {"ref": _REF, "relation": {"type": "string", "enum": list(RELATIONS)}}}]}
_META = {
    "aliases": {"type": "array", "items": _STR, "maxItems": 32, "description": "Short names to find it again."},
    "valid_from": {"type": "string", "description": "UTC time, e.g. 2026-01-31T00:00:00Z."},
    "valid_until": {"type": "string", "description": "UTC time after which it no longer applies."},
    "preconditions": {"type": "object", "description": "Exact conditions a search must supply to see it."},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1, "description": "Declared, not computed."},
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
          "Search current, valid memory. Withdrawn, superseded or expired versions are never returned. "
          "Results carry artifact_id and the exact ref.",
          {"query": {"type": "string", "description": "Keywords or a question."},
           "kinds": {"type": "array", "items": _KIND},
           "conditions": {"type": "object", "description": "Facts about the current situation, matched "
                                                           "exactly against stored preconditions."},
           "as_of": {"type": "string", "description": "UTC time to check validity at; default now."},
           "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
           "max_chars": {"type": "integer", "minimum": 200, "maximum": 16000}},
          ["query"], read_only=True, idempotent=True),
    _tool("memory_read", "Read one version",
          "Read one exact version. If it is no longer valid, the result says why and does not return it.",
          {"ref": _REF}, ["ref"], read_only=True, idempotent=True),
    _tool("memory_remember", "Remember a source",
          "Store a new fact, decision, document or procedure the user stated or confirmed. Returns its "
          "artifact_id and ref. To change something already stored, use memory_correct.",
          {"text": {"type": "string", "description": "Self-contained statement, with its date if known."},
           "kind": _KIND, "source_id": {"type": "string", "description": "Optional stable identifier."},
           **_META}, ["text"]),
    _tool("memory_derive", "Derive from exact parents",
          "Store a summary, conclusion or procedure built from exact parent versions. If a parent is later "
          "corrected or withdrawn, this artifact stops being readable.",
          {"text": _STR, "parents": {"type": "array", "items": _PARENT, "minItems": 1, "maxItems": 64},
           "kind": _KIND, "artifact_id": _STR, **_META}, ["text", "parents"]),
    _tool("memory_correct", "Correct an artifact",
          "Replace the current version of an artifact, only if it is still expected_version. Unspecified "
          "metadata is kept. Artifacts derived from the old version stop being readable.",
          {"artifact_id": _STR, "text": _STR, "expected_version": {"type": "string",
                                                                   "description": "version_id you read."},
           "parents": {"type": "array", "items": _PARENT, "minItems": 1, "maxItems": 64}, **_META},
          ["artifact_id", "text", "expected_version"]),
    _tool("memory_explain", "Explain an artifact",
          "Show what an artifact depends on and what depends on it, whether it is readable and why. "
          "Metadata only, never content. Give artifact_id or ref.",
          {"artifact_id": _STR, "ref": _REF}, read_only=True, idempotent=True),
    _tool("memory_plan_withdrawal", "Plan a withdrawal",
          "List what a withdrawal of this artifact would block, without changing anything.",
          {"artifact_id": _STR}, ["artifact_id"], read_only=True, idempotent=True),
    _tool("memory_withdraw", "Withdraw an artifact",
          "Withdraw an artifact the user says is wrong, outdated or must be forgotten. Everything derived "
          "from it stops being readable too. Not physical erasure.",
          {"artifact_id": _STR, "reason": {"type": "string", "maxLength": 500},
           "event_id": {"type": "string", "description": "Optional key that makes a retry idempotent."}},
          ["artifact_id", "reason"], destructive=True, idempotent=True),
    _tool("memory_learn", "Learn a lesson",
          "After a task, keep its trace and the feedback it got as provenance and store the lesson drawn "
          "from them. Only the lesson is searchable; withdrawing the trace or the feedback blocks it.",
          {"trace": _RAW, "feedback": _RAW, "lesson": {"type": "string"}, "kind": _KIND, "lesson_id": _STR,
           "aliases": _META["aliases"], "preconditions": _META["preconditions"],
           "valid_from": _META["valid_from"], "valid_until": _META["valid_until"],
           "confidence": _META["confidence"]},
          ["trace", "feedback", "lesson"]),
    _tool("memory_notices", "Check notices",
          "Artifacts this session was shown that have since been withdrawn, invalidated or superseded. "
          "Each is reported once; tool results also carry them as memory_notices.",
          {}, read_only=True),
)
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

    def __init__(self, memory, *, read_only=False, allow_withdraw=True):
        self.memory = memory
        names = {t["name"] for t in TOOLS}
        if read_only:
            names &= READ_ONLY
        if not allow_withdraw:
            names.discard("memory_withdraw")
        self._tools = [t for t in TOOLS if t["name"] in names]
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
            if not _matches(schema["properties"][key], value):
                raise MemoryError("invalid_argument:" + key)

    def call(self, name, args, session):
        """Return (payload, is_error). Refusals become tool errors the model can read."""
        try:
            self._check(name, args)
            payload = self._run(name, dict(args), session)
            is_error = False
        except (MemoryError, ValueError, TypeError) as exc:
            payload, is_error = {"error": str(exc) or type(exc).__name__}, True
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
        if name == "memory_search":
            out = m.search(args.pop("query"), session=session, **args)
            reasons = {}
            for item in out["exclusions"]:
                reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
            return {"status": out["status"], "complete": out["complete"], "items": [
                {"artifact_id": i["artifact_id"], "ref": i["ref"], "kind": i["metadata"]["evidence_kind"],
                 "text": i["text"], "metadata": i["metadata"]} for i in out["items"]],
                "excluded": reasons}
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
            "instructions": INSTRUCTIONS}}


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


def main(argv=None):
    parser = argparse.ArgumentParser(prog="persistent-memory-mcp", description=__doc__.splitlines()[0])
    parser.add_argument("--store", default=os.environ.get("PERSISTENT_MEMORY_DIR"),
                        help="Store directory; default $PERSISTENT_MEMORY_DIR")
    parser.add_argument("--workspace", default=os.environ.get("PERSISTENT_MEMORY_WORKSPACE", "default"))
    parser.add_argument("--create", action="store_true", help="Create the store if it does not exist")
    parser.add_argument("--read-only", action="store_true",
                        help="Expose search, read, explain, plan_withdrawal and notices only")
    parser.add_argument("--no-withdraw", action="store_true", help="Do not expose memory_withdraw")
    parser.add_argument("--session", help="Ledger session id; default one new id per process")
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="persistent-memory-mcp: %(message)s")
    if not args.store:
        parser.error("--store or PERSISTENT_MEMORY_DIR is required")
    try:
        memory = PersistentMemory(os.path.expanduser(args.store), args.workspace, create=args.create)
    except MemoryError as exc:
        print("persistent-memory-mcp: cannot open store: " + str(exc)
              + (" (add --create to make a new one)" if str(exc) == "store_missing" else ""), file=sys.stderr)
        return 2
    toolbox = Toolbox(memory, read_only=args.read_only, allow_withdraw=not args.no_withdraw)
    session = Session(toolbox, args.session or "mcp-" + uuid.uuid4().hex)
    try:
        return serve(session, sys.stdin.buffer, sys.stdout.buffer)
    except (BrokenPipeError, KeyboardInterrupt):
        return 0


if __name__ == "__main__":
    sys.exit(main())
