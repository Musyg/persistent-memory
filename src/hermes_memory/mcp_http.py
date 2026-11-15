"""Streamable HTTP transport for the MCP server, Python standard library only.

One endpoint, ``/mcp``. POST carries one JSON-RPC message and is answered with JSON; GET
answers 405 because the server never starts a stream; DELETE ends a session. Each MCP
session gets its own ledger session, so notices follow the client that saw a version.

Off loopback a bearer token is required. Browser Origin headers are refused unless allowed.
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import os
import secrets
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import __version__
from .mcp_server import Session, _error

__all__ = ["make_server", "load_token"]

logger = logging.getLogger("persistent_memory.mcp")

MAX_BODY = 4 * 1024 * 1024
MAX_SESSIONS = 256
SESSION_IDLE_SECONDS = 24 * 3600
MIN_TOKEN_LENGTH = 32


def is_loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class Sessions:
    """MCP sessions held in memory; idle ones expire and the table is bounded."""

    def __init__(self, toolbox):
        self.toolbox = toolbox
        self._lock = threading.Lock()
        self._items = {}

    def open(self, message):
        now = time.monotonic()
        with self._lock:
            for sid in [s for s, (_, seen) in self._items.items() if now - seen > SESSION_IDLE_SECONDS]:
                del self._items[sid]
            if len(self._items) >= MAX_SESSIONS:
                return None, _error(message.get("id"), -32000, "Too many sessions")
        sid = secrets.token_urlsafe(32)
        session = Session(self.toolbox, "mcp-http-" + sid[:24])
        response = session.handle(message)
        if "error" in response:
            return None, response
        with self._lock:
            self._items[sid] = (session, time.monotonic())
        return sid, response

    def get(self, sid):
        with self._lock:
            item = self._items.get(sid or "")
            if item is None:
                return None
            self._items[sid] = (item[0], time.monotonic())
            return item[0]

    def close(self, sid):
        with self._lock:
            return self._items.pop(sid or "", None) is not None


def make_server(toolbox, host="127.0.0.1", port=8766, token=None, allowed_origins=()):
    if token is not None and (type(token) is not str or len(token) < MIN_TOKEN_LENGTH):
        raise ValueError("token_too_short")
    if token is None and not is_loopback(host):
        raise ValueError("network_token_required")
    sessions = Sessions(toolbox)
    origins = frozenset(allowed_origins)
    expected = None if token is None else ("Bearer " + token).encode("utf-8")
    # One call at a time against the store: the surface serializes anyway, and this keeps the
    # ledger order equal to the order replies are sent.
    calls = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "PersistentMemoryMCP/" + __version__
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def log_message(self, *args):
            pass

        def _send(self, status, body=None, headers=()):
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

        def _allowed(self):
            if urlsplit(self.path).path != "/mcp":
                self._send(404, {"error": "not_found"})
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin not in origins:
                self._send(403, {"error": "origin_not_allowed"})
                return False
            if expected is not None and not hmac.compare_digest(
                    self.headers.get("Authorization", "").encode("utf-8"), expected):
                self._send(401, {"error": "unauthorized"}, (("WWW-Authenticate", 'Bearer realm="mcp"'),))
                return False
            return True

        def do_GET(self):
            if self._allowed():
                self._send(405, {"error": "no_server_stream"}, (("Allow", "POST, DELETE"),))

        def do_DELETE(self):
            if self._allowed():
                if sessions.close(self.headers.get("Mcp-Session-Id")):
                    self._send(200)
                else:
                    self._send(404, {"error": "unknown_session"})

        def do_POST(self):
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
                message = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                return self._send(400, _error(None, -32700, "Parse error"))
            if isinstance(message, list):
                return self._send(400, _error(None, -32600, "Batching is not supported"))
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                return self._send(400, _error(None, -32600, "Invalid Request"))
            if "method" not in message:
                return self._send(202)
            method, ident = message.get("method"), message.get("id")
            if method == "server/discover":
                return self._send(200, _error(ident, -32601, "Method not found"))
            if method == "initialize":
                with calls:
                    sid, response = sessions.open(message)
                if sid is None:
                    return self._send(400 if response["error"]["code"] != -32000 else 503, response)
                return self._send(200, response, (("Mcp-Session-Id", sid),))
            sid = self.headers.get("Mcp-Session-Id")
            if not sid:
                return self._send(400, _error(ident, -32600, "Mcp-Session-Id required"))
            session = sessions.get(sid)
            if session is None:
                return self._send(404, _error(ident, -32600, "Unknown or expired session"))
            with calls:
                response = session.handle(message)
            if response is None:
                return self._send(202)
            self._send(200, response)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def _posix_permissions():
    """True where file mode bits and owner ids mean something (Linux, macOS)."""
    return os.name == "posix"


def load_token(path):
    """Read a bearer token from a regular file that only its owner can read."""
    p = Path(path)
    info = p.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError("token_file_must_be_regular")
    # Mode bits and owner ids only mean something on POSIX. On Windows (os.name == "nt") they are
    # synthesized, so the permission and owner checks are skipped there on purpose: access to the
    # token file is decided by its ACL, which is not inspected. Keep it in a per-user folder.
    if _posix_permissions():
        if info.st_mode & 0o077:
            raise ValueError("token_file_permissions_too_open")
        if info.st_uid != os.getuid():
            raise ValueError("token_file_not_owned")
    value = p.read_text(encoding="utf-8").strip()
    if len(value) < MIN_TOKEN_LENGTH:
        raise ValueError("token_too_short")
    return value
