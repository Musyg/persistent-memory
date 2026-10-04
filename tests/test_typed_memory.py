"""Real SQLite/core tests; no models, network or production sources imported."""

import importlib.util
import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

from hermes_memory.typed_memory import RetrievalError, TypedMemory, metadata


class TypedRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import hermes_memory.core as installed_core
        path = Path(installed_core.__file__)
        spec = importlib.util.spec_from_file_location("g3_actual_core", path)
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        authority = self.module.Authority.create(self.directory / "authority.sqlite", self.directory / "anchor.json")
        self.memory = self.module.Memory.create(self.directory / "memory.sqlite", authority)
        self.typed = TypedMemory(self.memory, self.directory / "index.sqlite")

    def tearDown(self):
        self.temp.cleanup()

    def put(self, source, text, attributes=None, workspace="demo", previous=None):
        return self.typed.put(workspace, source, text, attributes or {}, expected_version=previous)["ref"]

    def test_identifier_and_alias_absent_from_body(self):
        reference = self.put("ID-441", "A delivery waits by the door.", {"aliases": ["repère dépôt"]})
        self.typed.sync("demo")
        for query in ("ID-441", "repère dépôt"):
            result = self.typed.search("demo", query)
            self.assertEqual(result["items"][0]["ref"], reference)
            self.assertEqual(result["context"], "A delivery waits by the door.")

    def test_indexed_lexical_and_budget(self):
        self.put("large", "Window window window " + "long history " * 20)
        self.put("brief", "Window: shut the latch.")
        self.typed.sync("demo")
        result = self.typed.search("demo", "window", max_context_chars=30)
        self.assertEqual(result["context"], "Window: shut the latch.")
        self.assertLessEqual(result["context_chars"], 30)

    def test_index_stale_requires_explicit_sync(self):
        self.put("a", "orchid")
        self.typed.sync("demo")
        self.put("b", "orchid independent")
        stale = self.typed.search("demo", "orchid")
        self.assertEqual(stale["status"], "index_stale")
        self.assertEqual(stale["context"], "")

    def test_refetch_never_uses_corrupted_projection_text(self):
        self.put("a", "Original jasper text.")
        self.typed.sync("demo")
        with sqlite3.connect(self.directory / "index.sqlite") as connection:
            connection.execute("UPDATE lexical SET text='forged poison payload'")
        result = self.typed.search("demo", "poison")
        self.assertEqual(result["context"], "Original jasper text.")
        self.assertNotIn("poison", result["context"])

    def test_revocation_and_other_workspace(self):
        self.put("a", "violet old")
        self.put("b", "violet independent")
        self.put("c", "violet foreign", workspace="other")
        self.typed.sync("demo")
        self.memory.revoke_source("demo", "a", "withdraw-a")
        self.assertEqual(self.typed.search("demo", "violet")["status"], "index_stale")
        self.typed.sync("demo")
        self.assertEqual(self.typed.search("demo", "violet")["context"], "violet independent")

    def test_superseded_version_never_returns_for_history(self):
        first = self.put("rule", "Cotton rule.", {"valid_from": "2031-01-01T00:00:00Z", "valid_until": "2031-02-01T00:00:00Z"})
        self.put("rule", "Linen rule.", {"valid_from": "2031-02-01T00:00:00Z"}, previous=first["version_id"])
        self.typed.sync("demo")
        result = self.typed.search("demo", "rule", as_of="2031-01-15T00:00:00Z")
        self.assertEqual(result["context"], "")
        self.assertEqual(result["historical_version_access"], "unsupported")
        self.assertFalse(self.memory.read(first)["allowed"])

    def test_time_boundaries_and_missing_time(self):
        self.put("state", "gate open", {"valid_from": "2031-01-01T00:00:00Z", "valid_until": "2031-01-02T00:00:00Z"})
        self.typed.sync("demo")
        self.assertEqual(self.typed.search("demo", "gate")["context"], "")
        self.assertEqual(self.typed.search("demo", "gate", as_of="2031-01-01T00:00:00Z")["context"], "gate open")
        self.assertEqual(self.typed.search("demo", "gate", as_of="2031-01-02T00:00:00Z")["context"], "")

    def test_typed_preconditions_no_bool_integer_equivalence(self):
        self.put("procedure", "sensor procedure", {"evidence_kind": "procedure", "preconditions": {"off": True}})
        self.typed.sync("demo")
        for supplied in ({}, {"off": 1}, {"off": False}):
            self.assertEqual(self.typed.search("demo", "sensor", conditions=supplied)["context"], "")
        self.assertEqual(self.typed.search("demo", "sensor", conditions={"off": True})["context"], "sensor procedure")

    def test_kind_filter_does_not_promote_confidence(self):
        self.put("guess", "level predicted 90", {"evidence_kind": "hypothesis", "confidence": 1})
        self.put("measured", "level measured 20", {"evidence_kind": "observation", "confidence": 0.1})
        self.typed.sync("demo")
        self.assertEqual(self.typed.search("demo", "level", evidence_kinds=["observation"])["context"], "level measured 20")

    def test_concurrent_change_discards_response(self):
        self.put("a", "cobalt")
        self.typed.sync("demo")
        original = self.memory.validate
        def racing(refs):
            result = original(refs)
            self.memory.revoke_source("demo", "a", "racing-revoke")
            return result
        self.memory.validate = racing
        result = self.typed.search("demo", "cobalt")
        self.assertEqual(result["status"], "epoch_changed")
        self.assertEqual(result["context"], "")

    def test_unmanaged_and_capacity_refuse_false_completeness(self):
        self.put("a", "valid")
        self.memory.register_source("demo", "legacy", "legacy plain text")
        with self.assertRaisesRegex(RetrievalError, "sync_document_limit"):
            self.typed.sync("demo", max_documents=1)
        result = self.typed.sync("demo")
        self.assertEqual(result["unmanaged"], 1)
        self.assertFalse(self.typed.search("demo", "valid")["complete"])

    def test_byte_cap_preserves_previous_projection_exactly(self):
        self.put("a", "existing body")
        self.typed.sync("demo")
        path = self.directory / "index.sqlite"
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        self.put("b", "additional body")
        with self.assertRaisesRegex(RetrievalError, "sync_content_bytes_limit"):
            self.typed.sync("demo", max_content_bytes=1)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
        self.assertEqual(self.typed.search("demo", "existing")["status"], "index_stale")

    def test_validation_rejects_invalid_metadata_and_index_alias(self):
        for value in ({"confidence": True}, {"valid_from": "tomorrow"}, {"preconditions": {"x": []}}, {"arbitrary_rights": "admin"}):
            with self.assertRaises(RetrievalError):
                metadata(value)
        with self.assertRaisesRegex(RetrievalError, "index_must_be_separate"):
            TypedMemory(self.memory, self.memory.path)

    def test_empty_text_has_empty_context_despite_identity_hit(self):
        self.put("empty-record", "")
        self.typed.sync("demo")
        result = self.typed.search("demo", "empty-record")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["context"], "")
        self.assertTrue(result["context_empty"])

    def test_malformed_projection_reference_is_explicit_unavailable(self):
        self.put("a", "cobalt")
        self.typed.sync("demo")
        for value in ("{broken", "[]", '{"workspace":"demo"}'):
            with sqlite3.connect(self.directory / "index.sqlite") as connection:
                connection.execute("UPDATE documents SET ref=?", (value,))
            result = self.typed.search("demo", "cobalt")
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["reason"], "projection_reference_invalid")
            self.assertEqual(result["context"], "")

    def test_empty_index_schema_has_typed_error(self):
        with sqlite3.connect(self.directory / "index.sqlite") as connection:
            connection.execute("DELETE FROM index_schema")
        with self.assertRaisesRegex(RetrievalError, "index_schema_mismatch"):
            TypedMemory(self.memory, self.directory / "index.sqlite")


if __name__ == "__main__":
    unittest.main()
