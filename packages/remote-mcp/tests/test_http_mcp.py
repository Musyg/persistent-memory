"""Streamable HTTP MCP endpoint tests: a real server on an ephemeral loopback port."""

from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from hermes_agent_provenance import ProvenanceMemoryProvider
from hermes_agent_provenance.store import Store
from hermes_memory_mcp.server import load_token, make_server
from hermes_memory_mcp.tools import Tools

TOKEN = "t" * 40
PORT_TEXT = "Le serveur Orion-Test ecoute sur le port 9300."


class Endpoint:
    def __init__(self, store_dir: Path, *, token=TOKEN, origins=(), **tool_options):
        self.tools = Tools(Store(store_dir, "hermes"), **tool_options)
        self.server = make_server(self.tools, "127.0.0.1", 0, token, origins)
        self.port = self.server.server_address[1]
        self.token = token
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def request(self, method, body=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.token:
            h["Authorization"] = "Bearer " + self.token
        h.update(headers or {})
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        conn.request(method, "/mcp", body=data, headers=h)
        resp = conn.getresponse()
        payload = resp.read()
        conn.close()
        return resp.status, dict(resp.getheaders()), (json.loads(payload) if payload else None)

    def open_session(self, version="2025-06-18"):
        status, headers, body = self.request("POST", {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": version, "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        assert status == 200, (status, body)
        sid = headers["Mcp-Session-Id"]
        status, _, _ = self.request("POST", {"jsonrpc": "2.0", "method": "notifications/initialized"},
                                    {"Mcp-Session-Id": sid})
        assert status == 202, status
        return sid, body["result"]

    def rpc(self, sid, method, params=None, ident=2):
        status, _, body = self.request("POST", {"jsonrpc": "2.0", "id": ident, "method": method,
                                                "params": params or {}}, {"Mcp-Session-Id": sid})
        return status, body

    def tool(self, sid, name, **arguments):
        status, body = self.rpc(sid, "tools/call", {"name": name, "arguments": arguments})
        assert status == 200, (status, body)
        result = body["result"]
        return json.loads(result["content"][0]["text"]), result["isError"]


class HttpMcpTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="hermes-memory-mcp-")
        self.store_dir = Path(self._tmp.name) / "provenance"
        self.ep = Endpoint(self.store_dir)

    def tearDown(self):
        self.ep.close()
        self._tmp.cleanup()

    def test_initialize_negotiates_version_and_issues_session(self):
        _, result = self.ep.open_session("2025-06-18")
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertEqual(result["capabilities"], {"tools": {"listChanged": False}})
        _, result = self.ep.open_session("1999-01-01")
        self.assertEqual(result["protocolVersion"], "2025-11-25")

    def test_modern_discover_probe_is_refused_so_clients_fall_back(self):
        status, _, body = self.ep.request("POST", {"jsonrpc": "2.0", "id": 9, "method": "server/discover",
                                                   "params": {}})
        self.assertEqual(status, 200)
        self.assertEqual(body["error"]["code"], -32601)

    def test_session_is_required_and_must_be_known(self):
        status, _, _ = self.ep.request("POST", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(status, 400)
        status, _ = self.ep.rpc("not-a-session", "tools/list")
        self.assertEqual(status, 404)

    def test_tools_wait_for_initialized_notification(self):
        status, headers, _ = self.ep.request("POST", {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}}})
        sid = headers["Mcp-Session-Id"]
        _, body = self.ep.rpc(sid, "tools/list")
        self.assertEqual(body["error"]["code"], -32002)
        self.assertEqual(self.ep.rpc(sid, "ping")[1]["result"], {})

    def test_tools_list_with_annotations(self):
        sid, _ = self.ep.open_session()
        tools = {t["name"]: t for t in self.ep.rpc(sid, "tools/list")[1]["result"]["tools"]}
        self.assertEqual(set(tools), {"provenance_search", "provenance_explain", "provenance_remember",
                                      "provenance_withdraw"})
        self.assertTrue(tools["provenance_search"]["annotations"]["readOnlyHint"])
        self.assertTrue(tools["provenance_withdraw"]["annotations"]["destructiveHint"])

    def test_remember_then_search(self):
        sid, _ = self.ep.open_session()
        stored, err = self.ep.tool(sid, "provenance_remember", text=PORT_TEXT)
        self.assertFalse(err)
        found, err = self.ep.tool(sid, "provenance_search", query="Orion-Test port")
        self.assertFalse(err)
        self.assertEqual([r["source_id"] for r in found["results"]], [stored["source_id"]])

    def test_withdrawal_notice_reaches_only_the_session_that_saw_the_source(self):
        a, _ = self.ep.open_session()
        b, _ = self.ep.open_session()
        source = self.ep.tool(a, "provenance_remember", text=PORT_TEXT)[0]["source_id"]
        self.ep.tool(a, "provenance_search", query="Orion-Test port")
        self.ep.tool(b, "provenance_withdraw", source_id=source, reason="obsolete")
        first, _ = self.ep.tool(a, "provenance_search", query="Orion-Test port")
        self.assertEqual(first["results"], [])
        self.assertEqual(first["withdrawn_notice"]["withdrawn_source_ids"], [source])
        second, _ = self.ep.tool(a, "provenance_search", query="Orion-Test")
        self.assertNotIn("withdrawn_notice", second, "warned once per source")
        other, _ = self.ep.tool(b, "provenance_search", query="Orion-Test")
        self.assertNotIn("withdrawn_notice", other)

    def test_withdrawal_over_mcp_warns_a_hermes_agent_session_on_the_same_store(self):
        provider = ProvenanceMemoryProvider()
        provider.initialize("hermes-session", hermes_home=str(self.store_dir.parent), platform="cli")
        source = json.loads(provider.handle_tool_call("provenance_remember", {"text": PORT_TEXT}))["source_id"]
        self.assertIn("9300", provider.prefetch("port Orion-Test", session_id="hermes-session"))
        sid, _ = self.ep.open_session()
        self.ep.tool(sid, "provenance_withdraw", source_id=source, reason="obsolete")
        block = provider.prefetch("port Orion-Test", session_id="hermes-session")
        self.assertIn("Withdrawn sources", block)
        self.assertNotIn("9300", block)

    def test_invalid_arguments_and_unknown_source_are_tool_errors(self):
        sid, _ = self.ep.open_session()
        self.assertEqual(self.ep.tool(sid, "provenance_search", query="")[0]["error"], "invalid_query")
        self.assertEqual(self.ep.tool(sid, "provenance_search", query="x", extra=1)[0]["error"], "unknown_argument")
        out, err = self.ep.tool(sid, "provenance_withdraw", source_id="m-nope", reason="x")
        self.assertTrue(err)
        self.assertEqual(out["error"], "unknown_source")
        status, body = self.ep.rpc(sid, "tools/call", {"name": "no_such_tool", "arguments": {}})
        self.assertEqual(body["error"]["code"], -32602)

    def test_authentication_is_enforced(self):
        status, headers, _ = self.ep.request("POST", {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                                             {"Authorization": "Bearer wrong"})
        self.assertEqual(status, 401)
        self.assertIn("Bearer", headers["WWW-Authenticate"])
        with self.assertRaises(ValueError):
            make_server(self.ep.tools, "0.0.0.0", 0, None)
        with self.assertRaises(ValueError):
            make_server(self.ep.tools, "127.0.0.1", 0, "short")

    def test_browser_origins_are_refused_unless_allowed(self):
        status, _, _ = self.ep.request("POST", {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                                       {"Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        allowed = Endpoint(Path(self._tmp.name) / "other", origins=("https://ok.example",))
        try:
            status, _, _ = allowed.request("POST", {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}}},
                {"Origin": "https://ok.example"})
            self.assertEqual(status, 200)
        finally:
            allowed.close()

    def test_get_delete_batch_and_size_limits(self):
        self.assertEqual(self.ep.request("GET")[0], 405)
        sid, _ = self.ep.open_session()
        self.assertEqual(self.ep.request("DELETE", headers={"Mcp-Session-Id": sid})[0], 200)
        self.assertEqual(self.ep.rpc(sid, "tools/list")[0], 404)
        self.assertEqual(self.ep.request("POST", [{"jsonrpc": "2.0", "id": 1, "method": "ping"}])[0], 400)
        # The size is refused from the header, before any body is read; a real oversized body would
        # race the server's early close, so only the declared length is oversized here.
        self.assertEqual(self.ep.request("POST", raw=b"{}", headers={"Content-Length": "1048577"})[0], 413)
        self.assertEqual(self.ep.request("POST", raw=b"not json")[0], 400)

    def test_read_only_mode_exposes_reads_only(self):
        ro = Endpoint(Path(self._tmp.name) / "ro", allow_write=False)
        try:
            sid, _ = ro.open_session()
            names = {t["name"] for t in ro.rpc(sid, "tools/list")[1]["result"]["tools"]}
            self.assertEqual(names, {"provenance_search", "provenance_explain"})
            status, body = ro.rpc(sid, "tools/call", {"name": "provenance_remember", "arguments": {"text": "x"}})
            self.assertEqual(body["error"]["code"], -32602)
        finally:
            ro.close()

    def test_token_file_must_be_private(self):
        path = Path(self._tmp.name) / "token"
        path.write_text(TOKEN + "\n", encoding="utf-8")
        os.chmod(path, 0o644)
        with self.assertRaises(ValueError):
            load_token(str(path))
        os.chmod(path, 0o600)
        self.assertEqual(load_token(str(path)), TOKEN)
        path.write_text("short", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_token(str(path))


if __name__ == "__main__":
    unittest.main()
