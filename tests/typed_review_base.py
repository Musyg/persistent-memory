"""Independent synthetic retrieval checks against the installed Linux package."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from hermes_memory.typed_memory import CORE_SHA, RetrievalError, TypedMemory, canonical


class IndependentChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import hermes_memory.core as installed_core
        source = Path(installed_core.__file__)
        if hashlib.sha256(source.read_bytes()).hexdigest() != CORE_SHA:
            raise AssertionError("pinned core hash differs")
        spec = importlib.util.spec_from_file_location("independent_g3_core", source)
        cls.core = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.core
        spec.loader.exec_module(cls.core)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        authority = self.core.Authority.create(self.directory / "authority.db", self.directory / "anchor.json")
        self.memory = self.core.Memory.create(self.directory / "content.db", authority)
        self.index = self.directory / "index.db"
        self.typed = TypedMemory(self.memory, self.index)

    def put(self, identity="a", text="copper remembered", workspace="demo", attrs=None, previous=None):
        return self.typed.put(workspace, identity, text, attrs or {}, expected_version=previous)["ref"]

    def seed(self):
        ref = self.put()
        self.typed.sync("demo")
        return ref

    def assert_empty_status(self, result, status):
        self.assertEqual(result["status"], status)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["context"], "")
        self.assertFalse(result["complete"])

    def test_missing_anchor_refuses_cached_content(self):
        self.seed()
        anchor = self.memory.authority.anchor_path
        saved = anchor.read_bytes()
        anchor.unlink()
        self.assert_empty_status(self.typed.search("demo", "copper"), "unavailable")
        anchor.write_bytes(saved)
        self.assertEqual(self.typed.search("demo", "copper")["context"], "copper remembered")

    def test_missing_authoritative_content_refuses_cached_content(self):
        ref = self.seed()
        with sqlite3.connect(self.memory.path) as db:
            db.execute("DELETE FROM content WHERE ref=?", (self.core.key(ref),))
        self.assert_empty_status(self.typed.search("demo", "copper"), "unavailable")

    def test_missing_fts_table_is_unavailable_even_exact_identifier(self):
        self.seed()
        with sqlite3.connect(self.index) as db:
            db.execute("DROP TABLE lexical")
        self.assert_empty_status(self.typed.search("demo", "a"), "unavailable")

    def test_wrong_database_refused_without_reinitializing(self):
        wrong = self.directory / "other.db"
        with sqlite3.connect(wrong) as db:
            db.execute("CREATE TABLE unrelated(value TEXT)")
            db.execute("INSERT INTO unrelated VALUES ('preserve')")
        before = hashlib.sha256(wrong.read_bytes()).hexdigest()
        with self.assertRaisesRegex(RetrievalError, "index_backend_unavailable"):
            TypedMemory(self.memory, wrong)
        self.assertEqual(hashlib.sha256(wrong.read_bytes()).hexdigest(), before)

    def test_fts_unavailable_at_creation_has_explicit_error(self):
        class NoFTSConnection(sqlite3.Connection):
            def executescript(self, script):
                if "USING fts5" in script:
                    raise sqlite3.OperationalError("no such module: fts5")
                return super().executescript(script)
        original_connect = TypedMemory._connect
        def unavailable_connect(instance):
            db = sqlite3.connect(instance.index_path, factory=NoFTSConnection)
            db.row_factory = sqlite3.Row
            return db
        with patch.object(TypedMemory, "_connect", unavailable_connect):
            with self.assertRaisesRegex(RetrievalError, "index_backend_unavailable"):
                TypedMemory(self.memory, self.directory / "nofts.db")
        self.assertIs(TypedMemory._connect, original_connect)

    def test_sync_transaction_failure_rolls_back_old_projection(self):
        self.seed()
        with sqlite3.connect(self.index) as db:
            db.execute("CREATE TRIGGER refuse_insert BEFORE INSERT ON documents BEGIN SELECT RAISE(ABORT, 'synthetic sync failure'); END")
        before = hashlib.sha256(self.index.read_bytes()).hexdigest()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "synthetic sync failure"):
            self.typed.sync("demo")
        self.assertEqual(hashlib.sha256(self.index.read_bytes()).hexdigest(), before)
        self.assertEqual(self.typed.search("demo", "copper")["context"], "copper remembered")

    def test_document_cap_refusal_preserves_previous_bytes(self):
        self.seed()
        before = hashlib.sha256(self.index.read_bytes()).hexdigest()
        self.put("b", "copper extra")
        with self.assertRaisesRegex(RetrievalError, "sync_document_limit"):
            self.typed.sync("demo", max_documents=1)
        self.assertEqual(hashlib.sha256(self.index.read_bytes()).hexdigest(), before)
        self.assert_empty_status(self.typed.search("demo", "copper"), "index_stale")

    def test_foreign_reference_in_projection_is_refused(self):
        self.put()
        foreign = self.put("foreign", "foreign synthetic material", workspace="other")
        self.typed.sync("demo")
        with sqlite3.connect(self.index) as db:
            db.execute("UPDATE documents SET ref=?", (canonical(foreign),))
        with self.assertRaisesRegex(RetrievalError, "projection_scope_mismatch"):
            self.typed.search("demo", "copper")

    def test_old_reference_in_projection_cannot_recover_superseded_version(self):
        old = self.put("a", "copper old")
        self.put("a", "copper new", previous=old["version_id"])
        self.typed.sync("demo")
        with sqlite3.connect(self.index) as db:
            db.execute("UPDATE documents SET ref=?", (canonical(old),))
        result = self.typed.search("demo", "copper", as_of="2030-01-01T00:00:00Z")
        self.assertEqual(result["context"], "")
        self.assertEqual(result["exclusions"][0]["reason"], "version_not_current")

    def test_unicode_character_budget_includes_separators(self):
        text = "é🧪e\u0301"
        self.put("a", text, attrs={"aliases": ["pick"]})
        self.put("b", text, attrs={"aliases": ["pick"]})
        self.typed.sync("demo")
        for budget, count in ((0, 0), (len(text)-1, 0), (len(text), 1), (2*len(text)+1, 1), (2*len(text)+2, 2)):
            with self.subTest(budget=budget):
                result = self.typed.search("demo", "pick", max_context_chars=budget)
                self.assertEqual(len(result["items"]), count)
                self.assertEqual(result["context_chars"], len(result["context"]))
                self.assertLessEqual(result["context_chars"], budget)

    def test_reopen_persists_refs_and_metadata_without_sync(self):
        ref = self.put("a", "copper remembered", attrs={"confidence": 0.25, "evidence_kind": "observation"})
        self.typed.sync("demo")
        original = self.typed.search("demo", "copper")
        authority = self.core.Authority.open(self.memory.authority.path, self.memory.authority.anchor_path)
        memory = self.core.Memory.open(self.memory.path, authority)
        reopened = TypedMemory(memory, self.index).search("demo", "copper")
        self.assertEqual(original, reopened)
        self.assertEqual(reopened["items"][0]["ref"], ref)

    def test_change_after_snapshot_before_index_publish_is_stale(self):
        self.seed()
        original = self.typed.core.snapshot
        def racing(*args):
            result = original(*args)
            self.put("b", "copper concurrent")
            return result
        self.typed.core.snapshot = racing
        self.typed.sync("demo")
        self.assert_empty_status(self.typed.search("demo", "copper"), "index_stale")

    def test_candidate_cap_reports_nonexhaustive_coverage(self):
        self.put("a", "copper one")
        self.put("b", "copper two")
        self.typed.sync("demo")
        result = self.typed.search("demo", "copper", candidate_limit=1, top_k=1)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["coverage"]["candidate_count"], 1)
        self.assertTrue(result["coverage"]["candidate_truncated"])
        self.assertFalse(result["complete"])

    def test_authority_change_with_no_candidates_still_discards_response(self):
        self.seed()
        original = self.memory.validate
        def racing(refs):
            self.assertEqual(refs, [])
            result = original(refs)
            self.put("b", "violet newly present")
            return result
        self.memory.validate = racing
        self.assert_empty_status(self.typed.search("demo", "violet"), "epoch_changed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
