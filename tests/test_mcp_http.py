"""MCP over Streamable HTTP: sessions, access control and limits, on synthetic data."""
import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from hermes_memory import mcp_http, typed_client
from hermes_memory.mcp_http import load_token, make_server
from hermes_memory.mcp_server import Toolbox
from hermes_memory.persistent import PersistentMemory

TOKEN = "t" * 40
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}


class Base(unittest.TestCase):
    token = None
    origins = ()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "store"
        self.memory = PersistentMemory(self.root, "ws", create=True)
        self.server = make_server(Toolbox(self.memory), "127.0.0.1", 0, self.token, self.origins)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self._tmp.cleanup()

    def request(self, method="POST", body=None, headers=None, raw=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        all_headers = {"Content-Type": "application/json"}
        if self.token:
            all_headers["Authorization"] = "Bearer " + self.token
        all_headers.update(headers or {})
        connection.request(method, "/mcp", body=data, headers=all_headers)
        response = connection.getresponse()
        payload = response.read()
        connection.close()
        return response.status, dict(response.getheaders()), (json.loads(payload) if payload else None)

    def open(self):
        status, headers, reply = self.request(body=INIT)
        self.assertEqual(status, 200, reply)
        sid = headers["Mcp-Session-Id"]
        self.assertEqual(self.request(body={"jsonrpc": "2.0", "method": "notifications/initialized"},
                                      headers={"Mcp-Session-Id": sid})[0], 202)
        return sid

    def call(self, sid, name, **arguments):
        status, _, reply = self.request(body={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                              "params": {"name": name, "arguments": arguments}},
                                        headers={"Mcp-Session-Id": sid})
        self.assertEqual(status, 200)
        return reply["result"]["structuredContent"]


class Protocol(Base):
    def test_sessions(self):
        status, headers, reply = self.request(body=INIT)
        self.assertEqual(reply["result"]["protocolVersion"], "2025-06-18")
        sid = headers["Mcp-Session-Id"]
        self.assertGreaterEqual(len(sid), 32)
        listing = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
        self.assertEqual(self.request(body=listing, headers={"Mcp-Session-Id": sid})[2]["error"]["code"], -32002)
        self.request(body={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers={"Mcp-Session-Id": sid})
        self.assertEqual(len(self.request(body=listing, headers={"Mcp-Session-Id": sid})[2]["result"]["tools"]), 10)
        self.assertEqual(self.request(body=listing)[0], 400)
        self.assertEqual(self.request(body=listing, headers={"Mcp-Session-Id": "nope"})[0], 404)
        self.assertEqual(self.request("DELETE", headers={"Mcp-Session-Id": sid})[0], 200)
        self.assertEqual(self.request(body=listing, headers={"Mcp-Session-Id": sid})[0], 404)

    def test_other_methods_and_bodies(self):
        self.assertEqual(self.request("GET")[0], 405)
        self.assertEqual(self.request(body={"jsonrpc": "2.0", "id": 1, "method": "server/discover"})[2]["error"]["code"],
                         -32601)
        self.assertEqual(self.request(raw=b"not json")[0], 400)
        self.assertEqual(self.request(body=[INIT])[0], 400)
        self.assertEqual(self.request(body={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})[0], 400)
        self.assertEqual(self.request(raw=b"{}", headers={"Content-Length": str(4 * 1024 * 1024 + 1)})[0], 413)
        self.assertEqual(self.request(body={"jsonrpc": "2.0", "id": 9, "result": {}})[0], 202)

    def test_each_http_session_has_its_own_notices(self):
        seen, fresh = self.open(), self.open()
        self.call(seen, "memory_remember", text="Orion-Test ecoute sur 9300.", source_id="port")
        self.call(seen, "memory_search", query="Orion-Test 9300")
        PersistentMemory(self.root, "ws").withdraw("port", "changed")
        self.assertEqual(self.call(fresh, "memory_notices")["notices"], [])
        self.assertEqual([n["artifact_id"] for n in self.call(seen, "memory_notices")["notices"]], ["port"])

    def test_browser_origin_is_refused(self):
        self.assertEqual(self.request(body=INIT, headers={"Origin": "https://evil.example"})[0], 403)


class WithToken(Base):
    token = TOKEN
    origins = ("https://app.example",)

    def test_bearer_token_and_allowed_origin(self):
        self.assertEqual(self.request(body=INIT, headers={"Authorization": "Bearer wrong"})[0], 401)
        self.assertEqual(self.request(body=INIT, headers={"Origin": "https://app.example"})[0], 200)

    def test_configuration_refusals(self):
        with self.assertRaises(ValueError):
            make_server(Toolbox(self.memory), "0.0.0.0", 0)
        with self.assertRaises(ValueError):
            make_server(Toolbox(self.memory), "127.0.0.1", 0, "short")


class Tokens(unittest.TestCase):
    def test_load_token_checks_the_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "token"
            path.write_text(TOKEN + "\n")
            if os.name == "posix":  # permission bits and symlinks are checked on POSIX only
                path.chmod(0o644)
                with self.assertRaises(ValueError):
                    load_token(path)
                path.chmod(0o600)
                link = Path(folder) / "link"
                link.symlink_to(path)
                with self.assertRaises(ValueError):
                    load_token(link)
            self.assertEqual(load_token(path), TOKEN)
            path.write_text("short")
            with self.assertRaises(ValueError):
                load_token(path)


class TokenFilePortability(unittest.TestCase):
    """The POSIX mode and owner checks run on POSIX and are skipped, on purpose, where they cannot work."""

    def make(self, folder, mode):
        path = Path(folder) / "token"
        path.write_bytes((TOKEN + "\n").encode("ascii"))
        path.chmod(mode)
        return path

    def test_open_mode_is_refused_where_modes_exist(self):
        if os.name != "posix":
            return  # mode bits are synthesized here: there is nothing to assert
        with tempfile.TemporaryDirectory() as folder:
            path = self.make(folder, 0o644)
            with self.assertRaises(ValueError):
                mcp_http.load_token(path)
            with self.assertRaisesRegex(Exception, "private_token_file_required"):
                typed_client.token_from_file(path)
            path.chmod(0o600)
            self.assertEqual(mcp_http.load_token(path), TOKEN)
            self.assertEqual(typed_client.token_from_file(path), TOKEN)

    def test_token_is_opened_without_following_links_and_without_text_translation(self):
        flags = []
        genuine = os.open

        def spy(path, flag, *args, **kwargs):
            flags.append(flag)
            return genuine(path, flag, *args, **kwargs)
        with tempfile.TemporaryDirectory() as folder:
            path = self.make(folder, 0o600)
            with mock.patch.object(typed_client.os, "open", spy):
                self.assertEqual(typed_client.token_from_file(path), TOKEN)
        self.assertEqual(len(flags), 1)
        for name in ("O_NOFOLLOW", "O_BINARY"):  # each exists on one family of OS only
            if hasattr(os, name):
                self.assertTrue(flags[0] & getattr(os, name), name)

    def test_windows_branch_ignores_mode_and_owner_but_not_links_or_content(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make(folder, 0o644)
            with mock.patch.object(mcp_http, "_posix_permissions", return_value=False), \
                    mock.patch.object(typed_client, "_posix_permissions", return_value=False):
                self.assertEqual(mcp_http.load_token(path), TOKEN)
                self.assertEqual(typed_client.token_from_file(path), TOKEN)
                path.write_text("short")
                with self.assertRaises(ValueError):
                    mcp_http.load_token(path)
                with self.assertRaisesRegex(Exception, "invalid_token_size"):
                    typed_client.token_from_file(path)
                path.write_bytes((TOKEN + "\n").encode("ascii"))
                link = Path(folder) / "link"
                try:
                    link.symlink_to(path)
                except OSError:
                    return  # this account cannot create links: the lstat check has nothing to refuse
                with self.assertRaises(ValueError):
                    mcp_http.load_token(link)
                with self.assertRaisesRegex(Exception, "private_token_file_required"):
                    typed_client.token_from_file(link)


class Command(unittest.TestCase):
    def test_http_transport_from_the_command_line(self):
        with tempfile.TemporaryDirectory() as folder:
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            process = subprocess.Popen([sys.executable, "-m", "hermes_memory.mcp_server", "--store",
                                        str(Path(folder) / "s"), "--create", "--transport", "http", "--port", "0"],
                                       stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=env, text=True, encoding='utf-8')
            try:
                line = process.stderr.readline()
                port = int(re.search(r":(\d+)/mcp", line).group(1))
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
                connection.request("POST", "/mcp", body=json.dumps(INIT), headers={"Content-Type": "application/json"})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read())["result"]["serverInfo"]["name"], "persistent-memory")
                connection.close()
            finally:
                process.terminate()
                process.wait(timeout=60)
                process.stderr.close()
                process.stdout.close()

    def test_qdrant_needs_an_embedder(self):
        with tempfile.TemporaryDirectory() as folder:
            completed = subprocess.run([sys.executable, "-m", "hermes_memory.mcp_server", "--store",
                                        str(Path(folder) / "s"), "--create", "--qdrant-url", "http://127.0.0.1:1"],
                                       input=b"", capture_output=True, timeout=60,
                                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            self.assertEqual(completed.returncode, 2)
            self.assertIn(b"qdrant_needs_embed_url_and_embed_model", completed.stderr)


if __name__ == "__main__":
    unittest.main()
