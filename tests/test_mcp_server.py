"""The stdio MCP server, in process and as a real subprocess, on synthetic data."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hermes_memory.mcp_server import SUPPORTED_VERSIONS, Session, Toolbox
from hermes_memory.persistent import PersistentMemory

PORT = "Le serveur Orion-Test ecoute sur le port 9300."
INIT = {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}


class Client:
    """Drives a Session the way an MCP client would."""

    def __init__(self, session):
        self.session, self.next_id = session, 0

    def request(self, method, params=None):
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            message["params"] = params
        return self.session.handle(message)

    def notify(self, method):
        return self.session.handle({"jsonrpc": "2.0", "method": method})

    def open(self, version="2025-11-25"):
        reply = self.request("initialize", dict(INIT, protocolVersion=version))
        self.notify("notifications/initialized")
        return reply

    def call(self, name, **arguments):
        reply = self.request("tools/call", {"name": name, "arguments": arguments})
        result = reply["result"]
        return json.loads(result["content"][0]["text"]), result


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Path(self._tmp.name) / "store"
        self.memory = PersistentMemory(self.store, "ws", create=True)

    def tearDown(self):
        self._tmp.cleanup()

    def client(self, session_id="s1", version="2025-11-25", **flags):
        client = Client(Session(Toolbox(self.memory, **flags), session_id))
        client.open(version)
        return client


class Handshake(Base):
    def test_version_negotiation(self):
        for version in SUPPORTED_VERSIONS:
            reply = Client(Session(Toolbox(self.memory), "s")).request("initialize", dict(INIT, protocolVersion=version))
            self.assertEqual(reply["result"]["protocolVersion"], version)
        reply = Client(Session(Toolbox(self.memory), "s")).request("initialize", dict(INIT, protocolVersion="2099-01-01"))
        self.assertEqual(reply["result"]["protocolVersion"], SUPPORTED_VERSIONS[0])
        self.assertIn("instructions", reply["result"])
        self.assertEqual(reply["result"]["capabilities"], {"tools": {"listChanged": False}})

    def test_gate_discover_and_errors(self):
        client = Client(Session(Toolbox(self.memory), "s"))
        self.assertEqual(client.request("ping")["result"], {})
        self.assertEqual(client.request("server/discover")["error"]["code"], -32601)
        self.assertEqual(client.request("tools/list")["error"]["code"], -32002)
        self.assertEqual(client.request("initialize", {"protocolVersion": 1})["error"]["code"], -32602)
        client.open()
        self.assertEqual(client.request("initialize", INIT)["error"]["code"], -32600)
        self.assertEqual(client.request("resources/list")["error"]["code"], -32601)
        self.assertEqual(client.session.handle([{"jsonrpc": "2.0"}])["error"]["code"], -32600)
        self.assertIsNone(client.session.handle({"jsonrpc": "2.0", "id": 9, "result": {}}))

    def test_tool_sets(self):
        names = lambda c: sorted(t["name"] for t in c.request("tools/list")["result"]["tools"])
        self.assertEqual(len(names(self.client())), 10)
        self.assertEqual(names(self.client(read_only=True)),
                         ["memory_explain", "memory_notices", "memory_plan_withdrawal", "memory_read", "memory_search"])
        self.assertNotIn("memory_withdraw", names(self.client(allow_withdraw=False)))
        for tool in self.client().request("tools/list")["result"]["tools"]:
            self.assertFalse(tool["inputSchema"]["additionalProperties"])
            self.assertFalse(tool["annotations"]["openWorldHint"])

    def test_hidden_tools_cannot_be_called(self):
        client = self.client(read_only=True)
        reply = client.request("tools/call", {"name": "memory_remember", "arguments": {"text": PORT}})
        self.assertEqual(reply["error"]["code"], -32602)
        self.assertEqual(self.memory.search("Orion-Test")["items"], [])


class Tools(Base):
    def test_remember_search_read(self):
        client = self.client()
        stored, result = client.call("memory_remember", text=PORT, aliases=["orion port"])
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"], stored)
        found, _ = client.call("memory_search", query="Orion-Test port")
        self.assertEqual([i["artifact_id"] for i in found["items"]], [stored["artifact_id"]])
        self.assertEqual(found["items"][0]["kind"], "observation")
        read, _ = client.call("memory_read", ref=stored["ref"])
        self.assertEqual(read["text"], PORT)

    def test_structured_content_only_from_2025_06_18(self):
        _, result = self.client(version="2025-03-26").call("memory_remember", text=PORT)
        self.assertNotIn("structuredContent", result)

    def test_derive_correct_explain(self):
        client = self.client()
        src, _ = client.call("memory_remember", text=PORT, source_id="port")
        note, _ = client.call("memory_derive", text="Ouvrir 9300 sur le pare-feu Orion-Test.",
                              parents=[src["ref"]], kind="procedure", artifact_id="firewall")
        explained, _ = client.call("memory_explain", artifact_id="port")
        self.assertEqual([r["artifact_id"] for r in explained["dependents"]], ["firewall"])
        client.call("memory_correct", artifact_id="port", text="Port 9400.",
                    expected_version=src["ref"]["version_id"])
        read, _ = client.call("memory_read", ref=note["ref"])
        self.assertEqual(read["state"], "superseded")
        stale, result = client.call("memory_correct", artifact_id="port", text="Port 9500.",
                                    expected_version=src["ref"]["version_id"])
        self.assertTrue(result["isError"])
        self.assertEqual(stale["error"], "version_conflict")

    def test_plan_and_withdraw(self):
        client = self.client()
        src, _ = client.call("memory_remember", text=PORT, source_id="port")
        client.call("memory_derive", text="Ouvrir 9300.", parents=[src["ref"]], artifact_id="child")
        plan, _ = client.call("memory_plan_withdrawal", artifact_id="port")
        self.assertEqual([r["artifact_id"] for r in plan["dependents"]], ["child"])
        out, result = client.call("memory_withdraw", artifact_id="port", reason="obsolete", event_id="e1")
        self.assertFalse(result["isError"])
        self.assertEqual(out["mode"], "revoke_source")
        found, _ = client.call("memory_search", query="Orion-Test 9300")
        self.assertEqual(found["items"], [])

    def test_learn(self):
        client = self.client()
        out, _ = client.call("memory_learn", trace={"task": "export CSV Orion-Test", "attempt": "sans BOM"},
                             feedback={"success": False, "violation": "bom_required"},
                             lesson="Pour Orion-Test, exporter le CSV avec BOM.")
        found, _ = client.call("memory_search", query="CSV Orion-Test BOM", kinds=["procedure"])
        self.assertEqual([i["artifact_id"] for i in found["items"]], [out["lesson"]["artifact_id"]])
        self.assertTrue(found["complete"])

    def test_argument_errors_are_tool_errors(self):
        client = self.client()
        for arguments, reason in (({"text": PORT, "colour": "red"}, "unknown_argument:colour"),
                                  ({}, "missing_argument:text"),
                                  ({"text": 42}, "invalid_argument:text"),
                                  ({"text": PORT, "confidence": True}, "invalid_argument:confidence"),
                                  ({"text": PORT, "kind": "rumour"}, "invalid_evidence_kind")):
            out, result = client.call("memory_remember", **arguments)
            self.assertTrue(result["isError"], arguments)
            self.assertEqual(out["error"], reason)
        out, _ = client.call("memory_explain")
        self.assertEqual(out["error"], "give_artifact_id_or_ref")

    def test_null_optional_arguments_mean_absent(self):
        # Some framework adapters (CrewAI's) send every unset optional field as null.
        client = self.client()
        out, result = client.call("memory_remember", text=PORT, kind=None, source_id=None, aliases=None,
                                  valid_from=None, valid_until=None, preconditions=None,
                                  confidence=None)
        self.assertFalse(result.get("isError"), out)
        found, result = client.call("memory_search", query="Orion-Test 9300", kinds=None, as_of=None, conditions=None,
                                    top_k=None, max_chars=None)
        self.assertFalse(result.get("isError"), found)
        self.assertEqual([i["artifact_id"] for i in found["items"]], [out["artifact_id"]])
        for arguments, reason in (({"text": None}, "invalid_argument:text"),
                                  ({"text": PORT, "colour": None}, "unknown_argument:colour")):
            refused, result = client.call("memory_remember", **arguments)
            self.assertTrue(result["isError"], arguments)
            self.assertEqual(refused["error"], reason)


class Notices(Base):
    def test_next_result_carries_the_notice_once(self):
        client = self.client("chat-1")
        src, _ = client.call("memory_remember", text=PORT, source_id="port")
        client.call("memory_search", query="Orion-Test port")
        self.memory.withdraw("port", "changed elsewhere")
        out, _ = client.call("memory_search", query="vert sapin")
        self.assertEqual([(n["artifact_id"], n["state"]) for n in out["memory_notices"]], [("port", "withdrawn")])
        again, _ = client.call("memory_search", query="vert sapin")
        self.assertNotIn("memory_notices", again)

    def test_sessions_are_separate(self):
        seen, other = self.client("seen"), self.client("other")
        seen.call("memory_remember", text=PORT, source_id="port")
        seen.call("memory_search", query="Orion-Test port")
        self.memory.withdraw("port", "obsolete")
        out, _ = other.call("memory_notices")
        self.assertEqual(out["notices"], [])
        out, _ = seen.call("memory_notices")
        self.assertEqual(len(out["notices"]), 1)


class Subprocess(Base):
    def run_server(self, lines, *flags):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        completed = subprocess.run([sys.executable, "-m", "hermes_memory.mcp_server", "--store", str(self.store),
                                    "--workspace", "ws", *flags],
                                   input=b"".join(json.dumps(m).encode() + b"\n" for m in lines) + b"not json\n\n",
                                   capture_output=True, env=env, timeout=60)
        return completed, [json.loads(line) for line in completed.stdout.splitlines()]

    def test_stdio_round_trip(self):
        lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INIT},
                 {"jsonrpc": "2.0", "method": "notifications/initialized"},
                 {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                  "params": {"name": "memory_remember", "arguments": {"text": PORT}}},
                 {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                  "params": {"name": "memory_search", "arguments": {"query": "Orion-Test port"}}}]
        completed, replies = self.run_server(lines)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual([r.get("id") for r in replies], [1, 2, 3, None])
        self.assertEqual(replies[3]["error"]["code"], -32700)
        self.assertEqual(replies[2]["result"]["structuredContent"]["items"][0]["text"], PORT)
        self.assertEqual(len(self.memory.search("Orion-Test port")["items"]), 1)

    def test_missing_store_exits_with_a_message(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        missing = Path(self._tmp.name) / "missing"
        completed = subprocess.run([sys.executable, "-m", "hermes_memory.mcp_server", "--store", str(missing)],
                                   input=b"", capture_output=True, env=env, timeout=60)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, b"")
        self.assertIn(b"--create", completed.stderr)
        self.assertFalse(missing.exists())

    def start(self, *flags, store=None):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-m", "hermes_memory.mcp_server", "--store", str(store or self.store),
                               "--workspace", "ws", *flags], input=b"", capture_output=True, env=env, timeout=60)

    def assert_clean_exit_2(self, completed, *words):
        self.assertEqual(completed.returncode, 2, completed.stderr)
        text = completed.stderr.decode("utf-8")
        self.assertNotIn("Traceback", text)
        self.assertEqual(len(text.strip().splitlines()), 1, text)
        for word in words:
            self.assertIn(word, text)

    def test_half_created_store_says_how_to_recover(self):
        (self.store / "content.db").unlink()
        for flags in ((), ("--create",)):
            completed = self.start(*flags)
            self.assert_clean_exit_2(completed, "store_incomplete", "delete the store folder", "restore content.db")
        self.assertFalse((self.store / "content.db").exists())

    def test_startup_failures_are_one_line_with_exit_2(self):
        (self.store / "ledger.db").write_bytes(b"this is not a database" * 100)  # sqlite3.DatabaseError
        self.assert_clean_exit_2(self.start(), "DatabaseError")
        blocked = Path(self._tmp.name) / "a-file"
        blocked.write_text("x")  # --create below a regular file: NotADirectoryError / FileExistsError
        self.assert_clean_exit_2(self.start("--create", store=blocked / "store"), "Error")

    def test_read_only_flag(self):
        lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INIT},
                 {"jsonrpc": "2.0", "method": "notifications/initialized"},
                 {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
        completed, replies = self.run_server(lines, "--read-only")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(replies[1]["result"]["tools"]), 5)


if __name__ == "__main__":
    unittest.main()
