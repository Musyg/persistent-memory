"""Independent regressions for G3-REVIEW-001/002; R3 qualification only.

Run with the same environment as test_independent.py on Linux.
"""
import sqlite3
import unittest

import typed_review_base as base
from typed_review_base import RetrievalError, TypedMemory


class ReviewEdges(unittest.TestCase):
    setUpClass = classmethod(base.IndependentChecks.setUpClass.__func__)
    setUp = base.IndependentChecks.setUp
    put = base.IndependentChecks.put
    seed = base.IndependentChecks.seed

    def assert_controlled_refusal(self, raw):
        self.seed()
        with sqlite3.connect(self.index) as db:
            db.execute("UPDATE documents SET ref=?", (raw,))
        try:
            result = self.typed.search("demo", "copper")
        except RetrievalError:
            return
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["context"], "")
        self.assertEqual(result["items"], [])

    def test_non_json_ref_controlled_refusal(self):
        self.assert_controlled_refusal("synthetic-not-json")

    def test_non_object_ref_controlled_refusal(self):
        self.assert_controlled_refusal("[]")

    def test_missing_workspace_ref_controlled_refusal(self):
        self.assert_controlled_refusal('{"artifact_id":"a","version_id":"v"}')

    def test_empty_index_schema_controlled_refusal(self):
        with sqlite3.connect(self.index) as db:
            db.execute("DELETE FROM index_schema")
        with self.assertRaises(RetrievalError):
            TypedMemory(self.memory, self.index)

    def test_empty_body_marks_context_empty(self):
        self.put("empty-id", "")
        self.typed.sync("demo")
        result = self.typed.search("demo", "empty-id")
        self.assertEqual(result["context"], "")
        self.assertEqual(result["context_chars"], 0)
        self.assertTrue(result["context_empty"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
