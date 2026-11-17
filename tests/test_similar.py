"""Near-duplicate entries are pointed out after a write, never merged."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hermes_memory.mcp_server import SIMILAR_MIN_OVERLAP, Session, Toolbox, similar_entries
from hermes_memory.persistent import PersistentMemory

from test_mcp_server import Client

PORT = "The staging database listens on port 6543."
PORT_NEW = "The staging database listens on port 6544."


class Similar(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.memory = PersistentMemory(Path(self._tmp.name) / "store", "ws", create=True)
        self.agent = Client(Session(Toolbox(self.memory), "agent-1"))
        self.agent.open()

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, tool, **arguments):
        out, result = self.agent.call(tool, **arguments)
        self.assertFalse(result["isError"], out)
        return out

    def test_a_near_duplicate_is_pointed_out_and_both_are_kept(self):
        first = self.write("memory_remember", text=PORT, source_id="db-port")
        self.assertNotIn("similar", first)
        second = self.write("memory_remember", text=PORT_NEW)
        self.assertEqual([s["artifact_id"] for s in second["similar"]], ["db-port"])
        self.assertEqual(second["similar"][0]["text"], PORT)
        self.assertGreaterEqual(second["similar"][0]["overlap"], SIMILAR_MIN_OVERLAP)
        self.assertIn("memory_correct", second["similar_hint"])
        found = [i["text"] for i in self.memory.search("staging database port")["items"]]
        self.assertEqual(sorted(found), sorted([PORT, PORT_NEW]))  # nothing merged

    def test_unrelated_or_loosely_related_text_is_not_flagged(self):
        self.write("memory_remember", text=PORT)
        self.assertNotIn("similar", self.write("memory_remember", text="The cat is called Mika."))
        self.assertNotIn("similar", self.write("memory_remember", text="The production database runs PostgreSQL."))

    def test_the_entry_itself_and_its_parents_are_left_out(self):
        port = self.write("memory_remember", text=PORT, source_id="db-port")
        self.assertNotIn("similar", self.write("memory_remember", text=PORT, source_id="db-port"))
        rule = self.write("memory_derive", text="The staging database listens on port 6543: open it.",
                          parents=[port["ref"]])
        self.assertNotIn("similar", rule)
        lesson = self.write("memory_learn", trace="deploy failed", feedback="port closed", lesson=PORT_NEW)
        similar = [s["artifact_id"] for s in lesson["similar"]]
        self.assertEqual(sorted(similar), sorted(["db-port", rule["artifact_id"]]))
        self.assertFalse(set(similar) & {lesson["lesson"]["artifact_id"], lesson["trace"]["artifact_id"],
                                         lesson["feedback"]["artifact_id"]})

    def test_the_session_is_told_when_a_shown_entry_goes(self):
        self.write("memory_remember", text=PORT, source_id="db-port")
        self.write("memory_remember", text=PORT_NEW)
        self.memory.withdraw("db-port", "decommissioned")
        notices, _ = self.agent.call("memory_notices")
        self.assertIn("db-port", [n["artifact_id"] for n in notices["notices"]])

    def test_withdrawn_entries_are_not_proposed(self):
        self.write("memory_remember", text=PORT, source_id="db-port")
        self.memory.withdraw("db-port", "decommissioned")
        self.assertNotIn("similar", self.write("memory_remember", text=PORT_NEW))

    def test_a_failed_check_does_not_fail_the_write(self):
        with mock.patch.object(PersistentMemory, "search", side_effect=OSError("disk")):
            out = self.write("memory_remember", text=PORT)
        self.assertNotIn("similar", out)
        self.assertEqual(self.memory.read(out["ref"])["text"], PORT)

    def test_review_mode_shows_it_on_the_proposal(self):
        self.write("memory_remember", text=PORT, source_id="db-port")
        reviewer = Client(Session(Toolbox(self.memory, review=True), "agent-2"))
        reviewer.open()
        out, result = reviewer.call("memory_remember", text=PORT_NEW)
        self.assertFalse(result["isError"])
        self.assertEqual(out["status"], "pending_review")
        self.assertEqual([s["artifact_id"] for s in out["similar"]], ["db-port"])

    def test_library_helper(self):
        self.memory.remember(PORT, source_id="db-port")
        self.assertEqual([s["artifact_id"] for s in similar_entries(self.memory, PORT_NEW)], ["db-port"])
        self.assertEqual(similar_entries(self.memory, PORT_NEW, exclude={"db-port"}), [])
        self.assertEqual(similar_entries(self.memory, "...!"), [])


if __name__ == "__main__":
    unittest.main()
