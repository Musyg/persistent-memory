"""Streamable HTTP MCP endpoint for the provenance store, Python standard library only.

One endpoint, ``/mcp``. POST carries JSON-RPC and is answered with ``application/json``;
GET answers 405 because no server-initiated stream is offered; DELETE ends a session.
Handshake-era protocol versions are served. A ``server/discover`` probe gets "method not
found", which tells modern clients to fall back to the ``initialize`` handshake.
"""

from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import logging
import os
import secrets
import stat
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

from . import __version__
from .tools import Tools, dumps

logger = logging.getLogger(__name__)

SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
MAX_BODY = 1_048_576
MAX_SESSIONS = 256
SESSION_IDLE_SECONDS = 24 * 3600
MIN_TOKEN_LENGTH = 32
INSTRUCTIONS = (
    "Long-term memory with provenance. Search before answering about past decisions or facts and cite the "
    "source_id you rely on. Store a fact only when the user states or confirms it. If a tool result carries "
    "a withdrawn_notice, stop using everything that came from those sources."
)


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class Sessions:
    """MCP sessions held in memory; idle ones expire, and the table is bounded."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, dict[str, Any]] = {}

    def create(self, protocol: str) -> Optional[str]:
        now = time.monotonic()
        with self._lock:
            for sid in [s for s, v in self._items.items() if now - v["seen"] > SESSION_IDLE_SECONDS]:
                del self._items[sid]
            if len(self._items) >= MAX_SESSIONS:
                return None
            sid = secrets.token_urlsafe(32)
            self._items[sid] = {"protocol": protocol, "ready": False, "seen": now}
            return sid

    def get(self, sid: Optional[str]) -> Optional[dict[str, Any]]:
        with self._lock:
            item = self._items.get(sid or "")
            if item is not None:
                item["seen"] = time.monotonic()
            return item

    def mark_ready(self, sid: str) -> None:
        with self._lock:
            if sid in self._items:
                self._items[sid]["ready"] = True

    def delete(self, sid: Optional[str]) -> bool:
        with self._lock:
            return self._items.pop(sid or "", None) is not None


def _error(ident: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}}


def make_server(tools: Tools, host: str = "127.0.0.1", port: int = 8766, token: Optional[str] = None,
                allowed_origins: tuple[str, ...] = ()) -> ThreadingHTTPServer:
    if token is not None and (not isinstance(token, str) or len(token) < MIN_TOKEN_LENGTH):
        raise ValueError("token_too_short")
    if token is None and not is_loopback(host):
        raise ValueError("network_token_required")
    sessions = Sessions()
    origins = frozenset(allowed_origins)

    class Handler(BaseHTTPRequestHandler):
        server_version = "HermesMemoryMCP/" + __version__
        sys_version = ""

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args: Any) -> None:
            pass

        def _send(self, status: int, body: Optional[dict[str, Any]] = None,
                  headers: tuple[tuple[str, str], ...] = ()) -> None:
            raw = b"" if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            for key, value in headers:
                self.send_header(key, value)
            if body is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _allowed(self) -> bool:
            if urlsplit(self.path).path != "/mcp":
                self._send(404, {"error": "not_found"})
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin not in origins:
                self._send(403, {"error": "origin_not_allowed"})
                return False
            if token is not None and not hmac.compare_digest(
                    self.headers.get("Authorization", "").encode("utf-8"), ("Bearer " + token).encode("utf-8")):
                self._send(401, {"error": "unauthorized"}, (("WWW-Authenticate", 'Bearer realm="mcp"'),))
                return False
            return True

        def do_GET(self) -> None:
            if self._allowed():
                self._send(405, {"error": "no_server_stream"}, (("Allow", "POST, DELETE"),))

        def do_DELETE(self) -> None:
            if self._allowed():
                if sessions.delete(self.headers.get("Mcp-Session-Id")):
                    self._send(200)
                else:
                    self._send(404, {"error": "unknown_session"})

        def do_POST(self) -> None:
            if not self._allowed():
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if self.headers.get("Transfer-Encoding") is not None or length <= 0:
                return self._send(400, _error(None, -32600, "Content-Length required"))
            if length > MAX_BODY:
                return self._send(413, _error(None, -32600, "Request too large"))
            raw = self.rfile.read(length)
            try:
                msg = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                return self._send(400, _error(None, -32700, "Parse error"))
            if isinstance(msg, list):
                return self._send(400, _error(None, -32600, "Batching is not supported"))
            if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
                return self._send(400, _error(None, -32600, "Invalid Request"))
            if "method" not in msg:  # a response from the client: nothing is pending, accept it
                return self._send(202)
            method, ident, params = msg.get("method"), msg.get("id"), msg.get("params", {})
            if not isinstance(method, str) or not isinstance(params, dict):
                return self._send(400, _error(ident, -32600, "Invalid Request"))
            if method == "server/discover":
                return self._send(200, _error(ident, -32601, "Method not found"))
            if method == "initialize":
                return self._initialize(ident, params)
            sid = self.headers.get("Mcp-Session-Id")
            if not sid:
                return self._send(400, _error(ident, -32600, "Mcp-Session-Id required"))
            session = sessions.get(sid)
            if session is None:
                return self._send(404, _error(ident, -32600, "Unknown or expired session"))
            if "id" not in msg:
                if method == "notifications/initialized":
                    sessions.mark_ready(sid)
                return self._send(202)
            self._send(200, self._dispatch(ident, method, params, sid, session))

        def _initialize(self, ident: Any, params: dict[str, Any]) -> None:
            requested = params.get("protocolVersion")
            if not isinstance(requested, str) or not isinstance(params.get("capabilities"), dict) \
                    or not isinstance(params.get("clientInfo"), dict):
                return self._send(400, _error(ident, -32602, "Invalid initialize params"))
            version = requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
            sid = sessions.create(version)
            if sid is None:
                return self._send(503, _error(ident, -32000, "Too many sessions"))
            result = {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "hermes-memory-mcp", "version": __version__},
                      "instructions": INSTRUCTIONS}
            self._send(200, {"jsonrpc": "2.0", "id": ident, "result": result}, (("Mcp-Session-Id", sid),))

        def _dispatch(self, ident: Any, method: str, params: dict[str, Any], sid: str,
                      session: dict[str, Any]) -> dict[str, Any]:
            if method == "ping":
                return {"jsonrpc": "2.0", "id": ident, "result": {}}
            if not session["ready"]:
                return _error(ident, -32002, "Initialization not completed")
            if method == "tools/list":
                return {"jsonrpc": "2.0", "id": ident, "result": {"tools": tools.list()}}
            if method == "tools/call":
                name, args = params.get("name"), params.get("arguments", {})
                if name not in tools.names() or not isinstance(args, dict):
                    return _error(ident, -32602, "Unknown tool or invalid arguments")
                try:
                    payload, is_error = tools.call(name, args, "mcp:" + sid)
                except Exception:  # never leak internals; the store fails closed
                    logger.exception("tool %s failed", name)
                    payload, is_error = {"error": "memory_unavailable"}, True
                return {"jsonrpc": "2.0", "id": ident, "result": {
                    "content": [{"type": "text", "text": dumps(payload)}], "isError": is_error}}
            return _error(ident, -32601, "Method not found")

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def load_token(path: str) -> str:
    """Read a bearer token from a file that only its owner can read."""
    p = Path(path)
    info = p.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError("token_file_must_be_regular")
    if info.st_mode & 0o077:
        raise ValueError("token_file_permissions_too_open")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise ValueError("token_file_not_owned")
    value = p.read_text(encoding="utf-8").strip()
    if len(value) < MIN_TOKEN_LENGTH:
        raise ValueError("token_too_short")
    return value


def main(argv: Optional[list[str]] = None) -> int:
    from hermes_agent_provenance.store import Store

    parser = argparse.ArgumentParser(prog="hermes-memory-mcp", description=__doc__.splitlines()[0])
    parser.add_argument("--store-dir", required=True,
                        help="Provenance store directory, e.g. $HERMES_HOME/provenance to share it with Hermes Agent")
    parser.add_argument("--create", action="store_true", help="Create the store if it does not exist yet")
    parser.add_argument("--workspace", default="hermes")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--token-file", help="Bearer token file (owner-only permissions); required off loopback")
    parser.add_argument("--allow-origin", action="append", default=[],
                        help="Browser Origin allowed to call the endpoint; repeatable. Default: none")
    parser.add_argument("--read-only", action="store_true", help="Expose search and explain only")
    parser.add_argument("--no-withdraw", action="store_true", help="Do not expose provenance_withdraw")
    args = parser.parse_args(argv)
    store_dir = Path(args.store_dir)
    if not (store_dir / "authority" / "authority.db").exists() and not args.create:
        parser.error(f"no store in {store_dir}; pass --create to start a new one")
    token = load_token(args.token_file) if args.token_file else None
    tools = Tools(Store(store_dir, args.workspace), allow_write=not args.read_only,
                  allow_withdraw=not args.no_withdraw)
    server = make_server(tools, args.host, args.port, token, tuple(args.allow_origin))
    print(f"hermes-memory-mcp {__version__} on http://{args.host}:{server.server_address[1]}/mcp "
          f"(tools: {', '.join(sorted(tools.names()))})", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
