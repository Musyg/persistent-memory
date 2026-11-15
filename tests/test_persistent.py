"""The operations surface, driven only through its public methods on synthetic data."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from hermes_memory.core import MemoryError
from hermes_memory.persistent import OPERATIONS, PersistentMemory

PORT = "Le serveur Orion-Test ecoute sur le port 9300."
COLOR = "La couleur de la marque Orion-Test est le vert sapin."


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "store"
        self.pm = PersistentMemory(self.root, "ws", create=True)

    def tearDown(self):
        self._tmp.cleanup()

    def ids(self, result):
        self.assertEqual(result["status"], "completed", result)
        return [item["artifact_id"] for item in result["items"]]

    def refused(self, reason, call, *args, **kwargs):
        with self.assertRaises(MemoryError) as caught:
            call(*args, **kwargs)
        self.assertEqual(str(caught.exception), reason)


class OpenAndRead(Base):
    def test_surface_lists_its_operations(self):
        self.assertEqual(len(OPERATIONS), 12)
        for op in OPERATIONS:
            self.assertTrue(callable(getattr(self.pm, op)), op)

    def test_missing_store_is_not_created_silently(self):
        self.refused("store_missing", PersistentMemory, Path(self._tmp.name) / "other", "ws")
        self.assertFalse((Path(self._tmp.name) / "other").exists())

    def test_half_created_store_is_refused_not_completed(self):
        # Authority exists, content.db does not (creation interrupted): fail closed, with or without create.
        sid = self.pm.remember(PORT)["artifact_id"]
        (self.root / "content.db").unlink()
        for create in (False, True):
            self.refused("store_incomplete", PersistentMemory, self.root, "ws", create=create)
        self.assertFalse((self.root / "content.db").exists())  # nothing was written to "repair" it
        (self.root / "content.db").write_bytes(b"")  # reserved but never filled
        self.refused("store_incomplete", PersistentMemory, self.root, "ws", create=True)
        self.assertEqual((self.root / "content.db").stat().st_size, 0)
        self.assertTrue(sid)

    def test_reopen_keeps_memory(self):
        sid = self.pm.remember(PORT)["artifact_id"]
        again = PersistentMemory(self.root, "ws")
        self.assertEqual(self.ids(again.search("Orion-Test port")), [sid])

    def test_read_returns_text_metadata_or_reason(self):
        out = self.pm.remember(PORT, kind="procedure", aliases=["orion port"])
        got = self.pm.read(out["ref"])
        self.assertTrue(got["allowed"])
        self.assertEqual(got["text"], PORT)
        self.assertEqual(got["metadata"]["evidence_kind"], "procedure")
        self.assertEqual(got["metadata"]["aliases"], ["orion port"])
        missing = dict(out["ref"], version_id="0" * 32)
        self.assertEqual(self.pm.read(missing)["reason"], "unknown_ref")

    def test_other_workspace_refs_are_refused(self):
        other = PersistentMemory(self.root, "other-ws")
        ref = other.remember(PORT)["ref"]
        self.refused("scope_mismatch", self.pm.read, ref)
        self.assertEqual(self.pm.search("Orion-Test")["items"], [])


class SearchAndRemember(Base):
    def test_remember_then_search(self):
        port = self.pm.remember(PORT)["artifact_id"]
        self.pm.remember(COLOR)
        self.assertEqual(self.ids(self.pm.search("port 9300")), [port])

    def test_alias_exact_match(self):
        sid = self.pm.remember(PORT, aliases=["Port Orion"])["artifact_id"]
        self.assertIn(sid, self.ids(self.pm.search("port orion")))

    def test_long_prompt_keeps_discriminating_words(self):
        sid = self.pm.remember(PORT)["artifact_id"]
        prompt = "Dis moi si tu te souviens sur quel port le serveur Orion-Test ecoute en ce moment"
        result = self.pm.search(prompt)
        self.assertIn(sid, self.ids(result))
        self.assertNotIn(" si ", " " + result["query_terms"] + " ")

    def test_kind_filter(self):
        self.pm.remember(PORT, kind="observation")
        proc = self.pm.remember("Pour redemarrer Orion-Test, vider le cache puis relancer.", kind="procedure")
        self.assertEqual(self.ids(self.pm.search("Orion-Test", kinds=["procedure"])), [proc["artifact_id"]])

    def test_validity_window_is_checked_now(self):
        self.pm.remember(PORT, valid_until="2001-01-01T00:00:00Z")
        result = self.pm.search("Orion-Test port")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["exclusions"][0]["reason"], "outside_declared_valid_time")

    def test_preconditions_need_matching_conditions(self):
        sid = self.pm.remember(PORT, preconditions={"env": "prod"})["artifact_id"]
        self.assertEqual(self.pm.search("Orion-Test port")["items"], [])
        self.assertEqual(self.ids(self.pm.search("Orion-Test port", conditions={"env": "prod"})), [sid])

    def test_existing_source_id_is_refused(self):
        self.pm.remember(PORT, source_id="orion-port")
        self.refused("version_conflict", self.pm.remember, "Le port est 9400.", source_id="orion-port")

    def test_invalid_inputs(self):
        self.refused("invalid_evidence_kind", self.pm.remember, PORT, kind="rumour")
        self.refused("invalid_text", self.pm.remember, "   ")
        self.refused("invalid_query", self.pm.search, "")

    def test_index_rebuilds_after_external_write(self):
        self.pm.remember(COLOR)
        self.pm.typed.put("ws", "written-elsewhere", PORT, {"evidence_kind": "observation"})
        self.assertEqual(self.ids(self.pm.search("9300")), ["written-elsewhere"])


class DeriveAndCorrect(Base):
    def test_derived_needs_a_derives_parent(self):
        src = self.pm.remember(PORT)["ref"]
        self.refused("derivation_required", self.pm.derive, "Resume.",
                     parents=[{"ref": src, "relation": "cites"}])
        self.refused("invalid_relation", self.pm.derive, "Resume.",
                     parents=[{"ref": src, "relation": "inspires"}])

    def test_correcting_a_parent_blocks_derived_but_not_citations(self):
        src = self.pm.remember(PORT, source_id="port")
        other = self.pm.remember(COLOR, source_id="color")
        summary = self.pm.derive("Orion-Test: port 9300, vert sapin.", parents=[src["ref"], other["ref"]],
                                 kind="document", artifact_id="summary")
        note = self.pm.derive("Voir aussi la couleur.",
                              parents=[other["ref"], {"ref": src["ref"], "relation": "cites"}],
                              kind="document", artifact_id="note")
        self.assertTrue(self.pm.read(summary["ref"])["allowed"])
        fixed = self.pm.correct("port", "Le serveur Orion-Test ecoute sur le port 9400.",
                                expected_version=src["ref"]["version_id"])
        self.assertEqual(self.pm.read(src["ref"])["state"], "superseded")
        self.assertEqual(self.pm.read(summary["ref"])["reason"], "version_not_current")
        self.assertTrue(self.pm.read(note["ref"])["allowed"])
        self.assertTrue(self.pm.read(fixed["ref"])["allowed"])
        self.assertEqual(self.ids(self.pm.search("9400")), ["port"])

    def test_compare_and_swap(self):
        src = self.pm.remember(PORT, source_id="port", aliases=["orion port"])
        first = self.pm.correct("port", "Port 9400.", expected_version=src["ref"]["version_id"])
        self.refused("version_conflict", self.pm.correct, "port", "Port 9500.",
                     expected_version=src["ref"]["version_id"])
        self.assertEqual(self.pm.read(first["ref"])["metadata"]["aliases"], ["orion port"])

    def test_correct_derived_keeps_parents_and_requires_them_current(self):
        src = self.pm.remember(PORT, source_id="port")
        d = self.pm.derive("Port 9300.", parents=[src["ref"]], artifact_id="fact")
        d2 = self.pm.correct("fact", "Le port documente est 9300.", expected_version=d["ref"]["version_id"])
        self.assertEqual(self.pm.explain("fact")["parents"][0]["ref"], src["ref"])
        self.pm.correct("port", "Port 9400.", expected_version=src["ref"]["version_id"])
        self.refused("version_not_current", self.pm.correct, "fact", "Encore 9300.",
                     expected_version=d2["ref"]["version_id"])

    def test_unknown_artifact(self):
        self.refused("unknown_artifact", self.pm.correct, "nope", "x", expected_version="0" * 32)
        self.refused("unknown_artifact", self.pm.explain, "nope")
        self.refused("unknown_artifact", self.pm.withdraw, "nope", "obsolete")


class ExplainAndWithdraw(Base):
    def test_explain_is_metadata_only(self):
        src = self.pm.remember("Code interne secret 4242.", source_id="secret")
        self.pm.derive("Le code existe.", parents=[src["ref"]], artifact_id="child")
        out = self.pm.explain("secret")
        self.assertNotIn("Code interne", json.dumps(out))
        self.assertEqual(out["kind"], "source")
        self.assertEqual([r["artifact_id"] for r in out["dependents"]], ["child"])
        child = self.pm.explain("child")
        self.assertEqual(child["parents"][0]["ref"]["artifact_id"], "secret")
        self.assertNotIn("Code interne", json.dumps(child))

    def test_withdraw_source_cascades(self):
        src = self.pm.remember(PORT, source_id="port")
        child = self.pm.derive("Orion-Test ecoute sur 9300.", parents=[src["ref"]], artifact_id="child")
        grand = self.pm.derive("Pare-feu Orion-Test: ouvrir 9300.", parents=[child["ref"]],
                               artifact_id="grand")
        plan = self.pm.plan_withdrawal("port")
        self.assertEqual(plan["mode"], "revoke_source")
        self.assertEqual(sorted(r["artifact_id"] for r in plan["dependents"]), ["child", "grand"])
        out = self.pm.withdraw("port", "port change", event_id="evt-1")
        self.assertTrue(out["covered_reads_blocked"])
        self.assertFalse(out["physical_erasure"])
        for ref in (src["ref"], child["ref"], grand["ref"]):
            self.assertEqual(self.pm.read(ref)["state"], "withdrawn")
        self.assertEqual(self.pm.search("Orion-Test 9300")["items"], [])
        self.assertEqual(self.pm.withdraw("port", "port change", event_id="evt-1")["epoch"], out["epoch"])

    def test_withdraw_purges_search_projections(self):
        src = self.pm.remember(PORT, source_id="port")
        with closing(sqlite3.connect(self.root / "content.db")) as c:
            before = [r[0] for r in c.execute("SELECT content FROM projection")]
        self.assertTrue(any("9300" in text for text in before))
        self.pm.withdraw("port", "obsolete")
        with closing(sqlite3.connect(self.root / "content.db")) as c:
            projected = [r[0] for r in c.execute("SELECT content FROM projection")]
        self.assertFalse(any("9300" in text for text in projected))
        with closing(sqlite3.connect(self.root / "index.db")) as c:
            indexed = [r[0] for r in c.execute("SELECT text FROM lexical")]
        self.assertFalse(any("9300" in text for text in indexed))
        self.assertEqual(self.pm.read(src["ref"])["reason"], "source_revoked")

    def test_withdraw_derived_invalidates_it_and_its_children_only(self):
        src = self.pm.remember(PORT, source_id="port")
        wrong = self.pm.derive("Orion-Test ecoute sur 9301.", parents=[src["ref"]], artifact_id="wrong")
        below = self.pm.derive("Ouvrir 9301.", parents=[wrong["ref"]], artifact_id="below")
        self.assertEqual(self.pm.plan_withdrawal("wrong")["mode"], "invalidate_derived")
        self.pm.withdraw("wrong", "mauvais port")
        self.assertEqual(self.pm.read(wrong["ref"])["state"], "invalidated")
        self.assertEqual(self.pm.read(below["ref"])["state"], "invalidated")
        self.assertTrue(self.pm.read(src["ref"])["allowed"])

    def test_withdraw_reason_is_bounded(self):
        self.pm.remember(PORT, source_id="port")
        self.refused("invalid_reason", self.pm.withdraw, "port", "")
        self.refused("invalid_reason", self.pm.withdraw, "port", "x" * 501)


class Learn(Base):
    TRACE = {"task": "exporter les ecritures Orion-Test en CSV", "attempt": "CSV sans BOM", "result": "refuse"}
    FEEDBACK = {"success": False, "violation": "bom_required", "check": "csv-import"}
    LESSON = "Pour le recepteur Orion-Test, exporter le CSV en UTF-8 avec BOM."

    def test_lesson_is_retrieved_and_parents_stay_out_of_search(self):
        out = self.pm.learn(self.TRACE, self.FEEDBACK, self.LESSON, aliases=["csv orion"])
        lesson_id = out["lesson"]["artifact_id"]
        result = self.pm.search("CSV Orion-Test BOM", kinds=["procedure"])
        self.assertEqual(self.ids(result), [lesson_id])
        self.assertTrue(result["complete"])
        self.assertEqual(self.ids(self.pm.search("violation bom_required attempt")), [])
        parents = {p["ref"]["artifact_id"] for p in self.pm.explain(lesson_id)["parents"]}
        self.assertEqual(parents, {out["trace"]["artifact_id"], out["feedback"]["artifact_id"]})
        self.assertTrue(self.pm.read(out["trace"])["allowed"])
        self.assertFalse(self.pm.read(out["trace"])["managed"])

    def test_withdrawing_feedback_blocks_the_lesson(self):
        out = self.pm.learn(self.TRACE, self.FEEDBACK, self.LESSON)
        self.pm.withdraw(out["feedback"]["artifact_id"], "feedback errone")
        self.assertEqual(self.pm.read(out["lesson"]["ref"])["state"], "withdrawn")
        self.assertEqual(self.pm.search("CSV Orion-Test BOM")["items"], [])

    def test_parents_must_be_raw(self):
        envelope = json.dumps({"schema": "hermes.typed-memory.v1", "text": "x", "metadata": {}})
        self.refused("trace_must_not_be_a_memory_envelope", self.pm.learn, envelope, self.FEEDBACK, self.LESSON)

    def test_failed_lesson_leaves_no_readable_parents(self):
        self.pm.learn(self.TRACE, self.FEEDBACK, self.LESSON, lesson_id="lesson")
        before = self.pm.search("CSV Orion-Test BOM")
        self.refused("kind_conflict", self.pm.learn, self.TRACE, self.FEEDBACK, "Autre lecon.",
                     lesson_id="lesson", kind="observation")
        after = self.pm.search("CSV Orion-Test BOM")
        self.assertTrue(after["complete"])
        self.assertEqual(after["coverage"]["unmanaged"], before["coverage"]["unmanaged"])


class Exposure(Base):
    def test_session_is_told_once_about_a_withdrawn_source(self):
        port = self.pm.remember(PORT, source_id="port")
        self.pm.remember(COLOR, source_id="color")
        self.pm.search("Orion-Test port", session="s1")
        self.pm.withdraw("port", "obsolete")
        notices = self.pm.notices("s1")["notices"]
        self.assertEqual([(n["artifact_id"], n["state"]) for n in notices], [("port", "withdrawn")])
        self.assertEqual(notices[0]["ref"], port["ref"])
        self.assertEqual(self.pm.notices("s1")["notices"], [])

    def test_only_sessions_that_saw_it_are_told(self):
        self.pm.remember(PORT, source_id="port")
        self.pm.search("Orion-Test port", session="saw")
        self.pm.search("vert sapin", session="never")
        self.pm.withdraw("port", "obsolete")
        self.assertEqual(self.pm.notices("never")["notices"], [])
        self.assertEqual(len(self.pm.notices("saw")["notices"]), 1)

    def test_correction_and_derived_exposure_are_reported(self):
        src = self.pm.remember(PORT, source_id="port")
        child = self.pm.derive("Orion-Test: 9300.", parents=[src["ref"]], artifact_id="child")
        self.pm.read(child["ref"], session="s")
        self.pm.correct("port", "Port 9400.", expected_version=src["ref"]["version_id"])
        notices = self.pm.notices("s")["notices"]
        self.assertEqual([(n["artifact_id"], n["state"]) for n in notices], [("child", "superseded")])

    def test_report_and_peek(self):
        self.pm.remember(PORT, source_id="port")
        self.pm.search("Orion-Test port", session="s1")
        self.assertEqual(self.pm.exposure_report()["sessions"], [])
        self.pm.withdraw("port", "obsolete")
        self.assertEqual(len(self.pm.notices("s1", mark=False)["notices"]), 1)
        report = self.pm.exposure_report()["sessions"]
        self.assertEqual(report[0]["session"], "s1")
        self.assertFalse(report[0]["invalid"][0]["session_notified"])
        self.pm.notices("s1")
        self.assertTrue(self.pm.exposure_report()["sessions"][0]["invalid"][0]["session_notified"])

    def test_external_exposure_is_validated(self):
        src = self.pm.remember(PORT, source_id="port")
        self.assertEqual(self.pm.record_exposure("s", [src["ref"]], "prompt")["recorded"], 1)
        other = PersistentMemory(self.root, "other-ws")
        self.refused("scope_mismatch", self.pm.record_exposure, "s", [other.remember(PORT)["ref"]])


if __name__ == "__main__":
    unittest.main()
