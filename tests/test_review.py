"""Review mode: agent writes become proposals that a person approves, on synthetic data."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hermes_memory.core import MemoryError
from hermes_memory.mcp_server import Session, Toolbox
from hermes_memory.persistent import PersistentMemory
from hermes_memory.review import WRITE_TOOLS, Proposals

from test_mcp_server import INIT, Client

PORT = "Le serveur Orion-Test ecoute sur le port 9300."
FIXED = "Le serveur Orion-Test ecoute sur le port 9301."
RULE = "Ouvrir le port 9300 sur le pare-feu Orion-Test."


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Path(self._tmp.name) / "store"
        self.memory = PersistentMemory(self.store, "ws", create=True)
        self.agent = Client(Session(Toolbox(self.memory, review=True), "agent-1"))
        self.agent.open()
        self.proposals = Proposals(self.store)

    def tearDown(self):
        self._tmp.cleanup()

    def approve(self, proposal_id):
        return self.proposals.approve(proposal_id, lambda workspace: PersistentMemory(self.store, workspace))

    def propose(self, tool, **arguments):
        out, result = self.agent.call(tool, **arguments)
        self.assertFalse(result["isError"], out)
        self.assertEqual(out["status"], "pending_review")
        return out["proposal_id"]

    def texts(self, query="Orion-Test port"):
        return [i["text"] for i in self.memory.search(query)["items"]]


class Proposing(Base):
    def test_every_write_tool_only_creates_a_proposal(self):
        source = self.memory.remember(PORT, source_id="orion-port")
        before = self.memory.explain("orion-port")
        reply = self.agent.request("tools/list")["result"]["tools"]
        tools = {t["name"]: t for t in reply}
        self.assertIn("memory_proposal_status", tools)
        for name in WRITE_TOOLS:
            self.assertTrue(tools[name]["description"].startswith("Review mode:"), name)
        ids = [self.propose("memory_remember", text="Le serveur Orion-Test tourne sous Linux."),
               self.propose("memory_derive", text=RULE, parents=[source["ref"]]),
               self.propose("memory_correct", artifact_id="orion-port", text=FIXED,
                            expected_version=source["ref"]["version_id"]),
               self.propose("memory_withdraw", artifact_id="orion-port", reason="test"),
               self.propose("memory_learn", trace="t", feedback="f", lesson="Verifier le port Orion-Test.")]
        self.assertEqual(len(set(ids)), 5)
        self.assertEqual(self.texts(), [PORT])
        self.assertEqual(self.memory.explain("orion-port"), before)
        self.assertEqual([p["proposal_id"] for p in self.proposals.list()], ids)
        self.assertEqual({p["state"] for p in self.proposals.list()}, {"pending"})

    def test_invalid_calls_are_refused_before_any_proposal(self):
        out, result = self.agent.call("memory_remember", text=PORT, colour="blue")
        self.assertTrue(result["isError"])
        self.assertEqual(out["error"], "unknown_argument:colour")
        out, result = self.agent.call("memory_correct", artifact_id="x", text=FIXED)
        self.assertEqual(out["error"], "missing_argument:expected_version")
        self.assertEqual(self.proposals.list(states=None), [])

    def test_instructions_tell_the_agent(self):
        session = Session(Toolbox(self.memory, review=True), "agent-2")
        reply = session.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INIT})
        self.assertIn("proposals that a person approves", reply["result"]["instructions"])
        plain = Session(Toolbox(self.memory), "agent-3")
        reply = plain.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INIT})
        self.assertNotIn("proposals", reply["result"]["instructions"])

    def test_read_only_and_review_are_exclusive(self):
        with self.assertRaises(ValueError):
            Toolbox(self.memory, read_only=True, review=True)

    def test_without_review_nothing_changes(self):
        toolbox = Toolbox(self.memory)
        self.assertNotIn("memory_proposal_status", toolbox.names())
        self.assertIsNone(toolbox.proposals)
        self.assertEqual(toolbox.call("memory_remember", {"text": PORT}, "s")[0]["artifact_id"] != "", True)
        self.assertEqual(self.texts(), [PORT])


class Deciding(Base):
    def test_approval_keeps_every_guarantee(self):
        first = self.approve(self.propose("memory_remember", text=PORT, source_id="orion-port"))
        self.assertEqual(first["state"], "approved")
        ref = first["result"]["ref"]
        self.assertEqual(self.texts(), [PORT])
        rule = self.approve(self.propose("memory_derive", text=RULE, parents=[ref]))
        self.assertEqual(sorted(self.texts()), sorted([PORT, RULE]))
        self.agent.call("memory_search", query="Orion-Test port")  # the agent is shown both
        fixed = self.approve(self.propose("memory_correct", artifact_id="orion-port", text=FIXED,
                                          expected_version=ref["version_id"]))
        self.assertEqual(fixed["state"], "approved")
        self.assertEqual(self.texts(), [FIXED])
        self.assertEqual(self.memory.read(rule["result"]["ref"])["state"], "superseded")
        out, _ = self.agent.call("memory_notices")
        self.assertIn(rule["result"]["artifact_id"], {n["artifact_id"] for n in out["notices"]})
        gone = self.approve(self.propose("memory_withdraw", artifact_id="orion-port", reason="decommissioned"))
        self.assertEqual(gone["result"]["event_id"], "review-" + gone["proposal_id"])
        self.assertEqual(self.texts(), [])

    def test_stale_correction_is_refused_not_forced(self):
        source = self.memory.remember(PORT, source_id="orion-port")
        v = source["ref"]["version_id"]
        a = self.propose("memory_correct", artifact_id="orion-port", text=FIXED, expected_version=v)
        b = self.propose("memory_correct", artifact_id="orion-port", text="port 9302", expected_version=v)
        self.assertEqual(self.approve(a)["state"], "approved")
        late = self.approve(b)
        self.assertEqual((late["state"], late["error"]), ("failed", "version_conflict"))
        self.assertEqual(self.texts(), [FIXED])
        out, _ = self.agent.call("memory_proposal_status", proposal_id=b)
        self.assertEqual((out["state"], out["error"]), ("failed", "version_conflict"))

    def test_a_decision_is_taken_once(self):
        a = self.propose("memory_remember", text=PORT)
        b = self.propose("memory_remember", text=FIXED)
        self.assertEqual(self.proposals.reject(a, "pas confirme")["note"], "pas confirme")
        self.assertEqual(self.approve(b)["state"], "approved")
        for decide in (lambda: self.approve(a), lambda: self.proposals.reject(b)):
            with self.assertRaises(MemoryError):
                decide()
        with self.assertRaisesRegex(MemoryError, "proposal_already_rejected"):
            self.approve(a)
        self.assertEqual(self.texts(), [FIXED])

    def test_status_is_scoped_and_cannot_decide(self):
        own = self.propose("memory_remember", text=PORT)
        other = PersistentMemory(self.store, "other")
        stranger = Client(Session(Toolbox(other, review=True), "agent-9"))
        stranger.open()
        out, result = stranger.call("memory_proposal_status", proposal_id=own)
        self.assertEqual((result["isError"], out["error"]), (True, "unknown_proposal"))
        self.assertEqual(stranger.call("memory_proposal_status")[0], {"proposals": []})
        out, _ = self.agent.call("memory_proposal_status")
        self.assertEqual([(p["proposal_id"], p["state"]) for p in out["proposals"]], [(own, "pending")])
        out, result = self.agent.call("memory_proposal_status", proposal_id=own, state="approved")
        self.assertEqual(out["error"], "unknown_argument:state")
        self.assertEqual(self.proposals.get(own)["state"], "pending")


class CommandLine(Base):
    def cli(self, *args, module="hermes_memory.persistent_cli", stdin=b""):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-m", module, *args], input=stdin, capture_output=True,
                              env=env, timeout=60)

    def test_server_flag_and_review_commands(self):
        lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INIT},
                 {"jsonrpc": "2.0", "method": "notifications/initialized"},
                 {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                  "params": {"name": "memory_remember", "arguments": {"text": PORT}}}]
        served = self.cli("--store", str(self.store), "--workspace", "ws", "--review",
                          module="hermes_memory.mcp_server",
                          stdin=b"".join(json.dumps(m).encode() + b"\n" for m in lines))
        self.assertEqual(served.returncode, 0, served.stderr)
        reply = json.loads(served.stdout.splitlines()[1])["result"]["structuredContent"]
        proposal_id = reply["proposal_id"]
        self.assertEqual(self.texts(), [])
        listed = self.cli("review", "list", "--store", str(self.store))
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn(proposal_id, listed.stdout.decode())
        self.assertIn("Orion-Test", listed.stdout.decode())
        approved = self.cli("review", "approve", proposal_id, "--store", str(self.store))
        self.assertEqual(approved.returncode, 0, approved.stderr)
        self.assertTrue(approved.stdout.decode().startswith(proposal_id + " approved"))
        self.assertEqual(self.texts(), [PORT])
        again = self.cli("review", "approve", proposal_id, "--store", str(self.store))
        self.assertEqual((again.returncode, again.stderr.decode().strip()),
                         (1, "persistent-memory review: proposal_already_approved"))
        empty = self.cli("review", "--store", str(self.store))
        self.assertIn("no proposals waiting", empty.stdout.decode())
        both = self.cli("--store", str(self.store), "--review", "--read-only", module="hermes_memory.mcp_server")
        self.assertEqual(both.returncode, 2)
        self.assertIn("cannot be combined", both.stderr.decode())


if __name__ == "__main__":
    unittest.main()
