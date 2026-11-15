"""One battery of memory scenarios, run through every way of reaching the memory.

Each adapter class below only says how to call an operation; the scenarios are shared, so
the Python surface, the MCP tool layer (stdio session), MCP over HTTP, the Hermes Agent
provider and the surface with a vector projection are held to the same behaviour.
"""
import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from hermes_memory.core import MemoryError
from hermes_memory.hermes_agent import PersistentMemoryProvider
from hermes_memory.mcp_http import make_server
from hermes_memory.mcp_server import Session, Toolbox
from hermes_memory.persistent import PersistentMemory
from hermes_memory.qdrant_projection import QdrantProjection
from qdrant_fake import FakeQdrant, HashEmbedder

PORT = "Le serveur Orion-Test ecoute sur le port 9300."
COLOR = "La couleur de la marque Orion-Test est le vert sapin."
INIT = {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "battery", "version": "0"}}


class Refused(Exception):
    pass


class Scenarios:
    """Mixed into one TestCase per adapter. self.a is the adapter, self.other a second actor."""

    def ids(self, query, **kwargs):
        return self.a.search(query, **kwargs)

    def test_remember_search_read(self):
        stored = self.a.remember(PORT, aliases=["orion port"])
        self.a.remember(COLOR)
        self.assertEqual(self.ids("port 9300"), [stored["artifact_id"]])
        self.assertIn(stored["artifact_id"], self.ids("orion port"))
        self.assertEqual(self.a.read(stored["ref"]), ("active", PORT))

    def test_correction_supersedes_derived_but_not_citations(self):
        port = self.a.remember(PORT, source_id="port")
        color = self.a.remember(COLOR, source_id="color")
        summary = self.a.derive("Orion-Test: port 9300 et vert sapin.", [port["ref"], color["ref"]],
                                artifact_id="summary", kind="document")
        note = self.a.derive("Voir aussi la couleur.", [color["ref"], {"ref": port["ref"], "relation": "cites"}],
                             artifact_id="note", kind="document")
        fixed = self.a.correct("port", "Le serveur Orion-Test ecoute sur le port 9400.", port["ref"]["version_id"])
        self.assertEqual(self.a.read(port["ref"])[0], "superseded")
        self.assertEqual(self.a.read(summary["ref"])[0], "superseded")
        self.assertEqual(self.a.read(note["ref"])[0], "active")
        self.assertEqual(self.a.read(fixed["ref"])[0], "active")
        self.assertEqual(self.ids("9400"), ["port"])
        self.assertNotIn("summary", self.ids("Orion-Test sapin 9300"))

    def test_compare_and_swap(self):
        port = self.a.remember(PORT, source_id="port")
        self.a.correct("port", "Port 9400.", port["ref"]["version_id"])
        with self.assertRaises(Refused) as caught:
            self.a.correct("port", "Port 9500.", port["ref"]["version_id"])
        self.assertEqual(str(caught.exception), "version_conflict")

    def test_withdraw_cascades(self):
        port = self.a.remember(PORT, source_id="port")
        child = self.a.derive("Ouvrir 9300 sur le pare-feu Orion-Test.", [port["ref"]], artifact_id="child")
        grand = self.a.derive("Checklist Orion-Test: verifier 9300.", [child["ref"]], artifact_id="grand")
        self.assertEqual(sorted(self.a.plan("port")), ["child", "grand"])
        self.a.withdraw("port", "port change")
        for ref in (port["ref"], child["ref"], grand["ref"]):
            self.assertEqual(self.a.read(ref)[0], "withdrawn")
        self.assertEqual(self.ids("Orion-Test 9300 pare-feu"), [])

    def test_withdraw_derived_only_invalidates_it(self):
        port = self.a.remember(PORT, source_id="port")
        wrong = self.a.derive("Orion-Test ecoute sur 9301.", [port["ref"]], artifact_id="wrong")
        self.a.withdraw("wrong", "mauvais port")
        self.assertEqual(self.a.read(wrong["ref"])[0], "invalidated")
        self.assertEqual(self.a.read(port["ref"])[0], "active")

    def test_lesson(self):
        out = self.a.learn({"task": "export CSV Orion-Test", "attempt": "sans BOM"},
                           {"success": False, "violation": "bom_required"},
                           "Pour le recepteur Orion-Test, exporter le CSV en UTF-8 avec BOM.")
        lesson = out["lesson"]["artifact_id"]
        self.assertEqual(self.ids("CSV Orion-Test BOM", kinds=["procedure"]), [lesson])
        self.assertEqual(self.ids("bom_required attempt"), [])
        self.a.withdraw(out["feedback"]["artifact_id"], "feedback errone")
        self.assertEqual(self.ids("CSV Orion-Test BOM"), [])

    def test_notice_once_after_external_withdrawal(self):
        self.a.remember(PORT, source_id="port")
        self.assertEqual(self.ids("Orion-Test port"), ["port"])
        self.other.withdraw("port", "changed elsewhere")
        self.assertEqual(self.a.notices(), [("port", "withdrawn")])
        self.assertEqual(self.a.notices(), [])

    def test_explain_is_metadata_only(self):
        src = self.a.remember("Code interne secret 4242.", source_id="secret")
        self.a.derive("Le code existe.", [src["ref"]], artifact_id="child")
        out = self.a.explain("secret")
        self.assertNotIn("Code interne", json.dumps(out))
        self.assertEqual([r["artifact_id"] for r in out["dependents"]], ["child"])

    def test_unknown_artifact_is_refused(self):
        with self.assertRaises(Refused) as caught:
            self.a.withdraw("nope", "obsolete")
        self.assertEqual(str(caught.exception), "unknown_artifact")

    def test_validity_and_preconditions(self):
        self.a.remember(PORT, source_id="old", valid_until="2001-01-01T00:00:00Z")
        self.a.remember("Orion-Test prod ecoute sur 9500.", source_id="prod", preconditions={"env": "prod"})
        self.assertEqual(self.ids("Orion-Test 9300"), [])
        self.assertNotIn("prod", self.ids("Orion-Test 9500"))
        self.assertEqual(self.ids("Orion-Test 9500", conditions={"env": "prod"}), ["prod"])


class SurfaceAdapter:
    def __init__(self, memory, session="battery"):
        self.m, self.session = memory, session

    def _do(self, call, *args, **kwargs):
        try:
            return call(*args, **kwargs)
        except MemoryError as exc:
            raise Refused(str(exc)) from None

    def remember(self, text, **kw):
        return self._do(self.m.remember, text, **kw)

    def search(self, query, **kw):
        return [i["artifact_id"] for i in self._do(self.m.search, query, session=self.session, **kw)["items"]]

    def read(self, ref):
        out = self._do(self.m.read, ref, session=self.session)
        return out["state"], out.get("text")

    def derive(self, text, parents, **kw):
        return self._do(self.m.derive, text, parents=parents, **kw)

    def correct(self, artifact_id, text, version):
        return self._do(self.m.correct, artifact_id, text, expected_version=version)

    def explain(self, artifact_id):
        return self._do(self.m.explain, artifact_id)

    def plan(self, artifact_id):
        return [r["artifact_id"] for r in self._do(self.m.plan_withdrawal, artifact_id)["dependents"]]

    def withdraw(self, artifact_id, reason):
        return self._do(self.m.withdraw, artifact_id, reason)

    def learn(self, trace, feedback, lesson):
        return self._do(self.m.learn, trace, feedback, lesson)

    def notices(self):
        return [(n["artifact_id"], n["state"]) for n in self.m.notices(self.session)["notices"]]


class ToolAdapter:
    """Everything through the ten MCP tools; subclasses only say how a tool is called."""

    def tool(self, name, **args):
        raise NotImplementedError

    def remember(self, text, **kw):
        return self.tool("memory_remember", text=text, **kw)

    def search(self, query, **kw):
        return [i["artifact_id"] for i in self.tool("memory_search", query=query, **kw)["items"]]

    def read(self, ref):
        out = self.tool("memory_read", ref=ref)
        return out["state"], out.get("text")

    def derive(self, text, parents, **kw):
        return self.tool("memory_derive", text=text, parents=parents, **kw)

    def correct(self, artifact_id, text, version):
        return self.tool("memory_correct", artifact_id=artifact_id, text=text, expected_version=version)

    def explain(self, artifact_id):
        return self.tool("memory_explain", artifact_id=artifact_id)

    def plan(self, artifact_id):
        return [r["artifact_id"] for r in self.tool("memory_plan_withdrawal", artifact_id=artifact_id)["dependents"]]

    def withdraw(self, artifact_id, reason):
        return self.tool("memory_withdraw", artifact_id=artifact_id, reason=reason)

    def learn(self, trace, feedback, lesson):
        return self.tool("memory_learn", trace=trace, feedback=feedback, lesson=lesson)

    def notices(self):
        return [(n["artifact_id"], n["state"]) for n in self.tool("memory_notices")["notices"]]


class StdioSessionAdapter(ToolAdapter):
    def __init__(self, memory):
        self.session, self.next_id = Session(Toolbox(memory), "battery-stdio"), 0
        self._rpc("initialize", INIT)
        self.session.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _rpc(self, method, params):
        self.next_id += 1
        return self.session.handle({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params})

    def tool(self, name, **args):
        result = self._rpc("tools/call", {"name": name, "arguments": args})["result"]
        payload = json.loads(result["content"][0]["text"])
        if result["isError"]:
            raise Refused(payload["error"])
        return payload


class HttpAdapter(ToolAdapter):
    def __init__(self, memory):
        self.server = make_server(Toolbox(memory), "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:%d/mcp" % self.server.server_address[1]
        self.sid, self.next_id = None, 0
        self._post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": INIT})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _post(self, message):
        request = urllib.request.Request(self.url, data=json.dumps(message).encode(), method="POST",
                                         headers={"Content-Type": "application/json",
                                                  "Accept": "application/json, text/event-stream"})
        if self.sid:
            request.add_header("Mcp-Session-Id", self.sid)
        with urllib.request.urlopen(request, timeout=30) as response:
            self.sid = self.sid or response.headers.get("Mcp-Session-Id")
            raw = response.read()
            return json.loads(raw) if raw else None

    def tool(self, name, **args):
        self.next_id += 1
        result = self._post({"jsonrpc": "2.0", "id": self.next_id, "method": "tools/call",
                             "params": {"name": name, "arguments": args}})["result"]
        payload = result["structuredContent"]
        if result["isError"]:
            raise Refused(payload["error"])
        return payload

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class HermesAdapter(ToolAdapter):
    def __init__(self, root, home):
        provider = PersistentMemoryProvider()
        provider.save_config({"store_dir": str(root), "workspace": "ws"}, str(home))
        provider.initialize("hermes-battery", hermes_home=str(home), platform="cli")
        self.provider = provider

    def tool(self, name, **args):
        payload = json.loads(self.provider.handle_tool_call(name, args))
        if "error" in payload:
            raise Refused(payload["error"])
        return payload


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "store"
        self.memory = PersistentMemory(self.root, "ws", create=True)
        self.other = SurfaceAdapter(PersistentMemory(self.root, "ws"), "someone-else")
        self.a = self.make_adapter()

    def tearDown(self):
        close = getattr(self.a, "close", None)
        if close:
            close()
        self._tmp.cleanup()


class SurfaceBattery(Scenarios, Base):
    def make_adapter(self):
        return SurfaceAdapter(self.memory)


class StdioToolBattery(Scenarios, Base):
    def make_adapter(self):
        return StdioSessionAdapter(self.memory)


class HttpBattery(Scenarios, Base):
    def make_adapter(self):
        return HttpAdapter(self.memory)


class HermesAgentBattery(Scenarios, Base):
    def make_adapter(self):
        return HermesAdapter(self.root, Path(self._tmp.name) / "hermes-home")


class QdrantProjectionBattery(Scenarios, Base):
    def make_adapter(self):
        self.qdrant = FakeQdrant()
        self.memory.attach_projection(QdrantProjection(self.memory, embed=HashEmbedder(), transport=self.qdrant))
        return SurfaceAdapter(self.memory)


if __name__ == "__main__":
    unittest.main()
