"""The Hermes Agent provider, driven without Hermes Agent through its stand-in base class.

tests_integration/test_hermes_agent_manager.py runs it inside Hermes Agent's MemoryManager.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hermes_memory.hermes_agent import PROVIDER_NAME, PersistentMemoryProvider, load_config, register
from hermes_memory.mcp_server import Session, Toolbox
from hermes_memory.persistent import PersistentMemory

PORT = "Le serveur Orion-Test ecoute sur le port 9300."


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name) / "hermes-home"

    def tearDown(self):
        self._tmp.cleanup()

    def provider(self, session="s1", **kwargs):
        p = PersistentMemoryProvider()
        p.initialize(session, hermes_home=str(self.home), platform="cli", **kwargs)
        return p

    def call(self, provider, tool, **args):
        return json.loads(provider.handle_tool_call(tool, args))


class Startup(Base):
    def test_half_created_store_is_one_clean_line(self):
        self.provider()
        (self.home / PROVIDER_NAME / "store" / "content.db").unlink()
        with self.assertRaises(RuntimeError) as caught:
            self.provider()
        message = str(caught.exception)
        self.assertIn("store_incomplete", message)
        self.assertEqual(len(message.splitlines()), 1)
        self.assertIsNone(caught.exception.__cause__)

    def test_config_is_written_with_lf_newlines(self):
        provider = PersistentMemoryProvider()
        with mock.patch("hermes_memory.hermes_agent.os.fdopen", wraps=os.fdopen) as opened:
            provider.save_config({"top_k": 7}, str(self.home))
        self.assertEqual(opened.call_args.kwargs.get("newline"), "\n")
        self.assertEqual((self.home / PROVIDER_NAME / "config.json").read_bytes().count(b"\r"), 0)
        self.assertEqual(load_config(self.home)["top_k"], 7)


class Provider(Base):
    def test_registration_and_name(self):
        registered = []

        class Ctx:
            def register_memory_provider(self, provider):
                registered.append(provider)

        register(Ctx())
        self.assertEqual([p.name for p in registered], [PROVIDER_NAME])
        self.assertEqual(PROVIDER_NAME, "persistent-memory")

    def test_tools_are_announced_before_initialize(self):
        # Hermes Agent's MemoryManager routes tools from the schemas it reads in add_provider().
        early = PersistentMemoryProvider()
        self.assertEqual(len(early.get_tool_schemas()), 10)
        self.assertIn("error", json.loads(early.handle_tool_call("memory_search", {"query": "x"})))

    def test_tool_schemas_are_the_mcp_tools(self):
        schemas = self.provider().get_tool_schemas()
        self.assertEqual(len(schemas), 10)
        for schema in schemas:
            self.assertEqual(set(schema), {"name", "description", "parameters"})
            self.assertFalse(schema["parameters"]["additionalProperties"])

    def test_prefetch_injects_validated_items(self):
        p = self.provider()
        stored = self.call(p, "memory_remember", text=PORT, source_id="port")
        block = p.prefetch("Sur quel port ecoute Orion-Test ?", session_id="s1")
        self.assertIn("[port]", block)
        self.assertIn("9300", block)
        self.assertEqual(p.recall_status().count, 1)
        self.assertEqual(stored["artifact_id"], "port")
        self.assertEqual(p.prefetch("ok", session_id="s1"), "")

    def test_withdrawn_item_gives_one_notice_and_is_gone(self):
        p = self.provider()
        self.call(p, "memory_remember", text=PORT, source_id="port")
        p.prefetch("Sur quel port ecoute Orion-Test ?", session_id="s1")
        PersistentMemory(self.home / PROVIDER_NAME / "store", "hermes").withdraw("port", "changed")
        block = p.prefetch("Sur quel port ecoute Orion-Test ?", session_id="s1")
        self.assertIn("No longer valid", block)
        self.assertIn("[port]", block)
        self.assertNotIn("ecoute", block)
        self.assertNotIn("No longer valid", p.prefetch("Sur quel port ecoute Orion-Test ?", session_id="s1"))
        self.assertNotIn("No longer valid", p.prefetch("Sur quel port ecoute Orion-Test ?", session_id="other"))

    def test_subagents_only_read(self):
        p = self.provider(agent_context="subagent")
        self.assertEqual(sorted(t["name"] for t in p.get_tool_schemas()),
                         ["memory_explain", "memory_notices", "memory_plan_withdrawal", "memory_read", "memory_search"])
        self.assertIn("error", self.call(p, "memory_remember", text=PORT))

    def test_withdraw_can_be_disabled(self):
        PersistentMemoryProvider().save_config({"allow_withdraw": "false"}, str(self.home))
        p = self.provider()
        self.assertNotIn("memory_withdraw", {t["name"] for t in p.get_tool_schemas()})
        self.assertEqual(load_config(self.home)["allow_withdraw"], "false")

    def test_refusals_are_tool_errors(self):
        p = self.provider()
        self.assertEqual(self.call(p, "memory_withdraw", artifact_id="nope", reason="x")["error"], "unknown_artifact")
        self.assertIn("error", self.call(p, "memory_bogus"))
        self.assertEqual(self.call(p, "memory_remember", text=PORT, colour="red")["error"], "unknown_argument:colour")

    def test_sync_turn_stores_nothing(self):
        p = self.provider()
        p.sync_turn("Le port est 9300", "Note.", session_id="s1")
        self.assertEqual(self.call(p, "memory_search", query="port 9300")["items"], [])

    def test_shared_store_with_an_mcp_client(self):
        shared = Path(self._tmp.name) / "shared"
        PersistentMemoryProvider().save_config({"store_dir": str(shared), "workspace": "team"}, str(self.home))
        p = self.provider()
        self.call(p, "memory_remember", text=PORT, source_id="port")
        mcp = Session(Toolbox(PersistentMemory(shared, "team")), "mcp")
        mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "c", "version": "0"}}})
        mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        reply = mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                            "params": {"name": "memory_search", "arguments": {"query": "Orion-Test 9300"}}})
        self.assertEqual([i["artifact_id"] for i in reply["result"]["structuredContent"]["items"]], ["port"])

    def test_system_prompt_and_session_switch(self):
        p = self.provider()
        self.assertIn("memory_withdraw", p.system_prompt_block())
        p.on_session_switch("s2")
        self.call(p, "memory_remember", text=PORT, source_id="port")
        self.call(p, "memory_search", query="Orion-Test 9300")
        PersistentMemory(self.home / PROVIDER_NAME / "store", "hermes").withdraw("port", "changed")
        self.assertIn("[port]", p.prefetch("hello there, anything new?", session_id="s2"))


if __name__ == "__main__":
    unittest.main()
