"""One-way export to Markdown notes (Obsidian or plain links), on synthetic data."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from hermes_memory.core import MemoryError
from hermes_memory.export import MANIFEST, export_store
from hermes_memory.persistent import PersistentMemory
from hermes_memory.persistent_cli import main

DAY = "Les mises en production ont lieu le mardi."
RULE = "Geler la branche main le lundi soir, avant la mise en production.\n\nPrevenir l'equipe support."
SECRET = "Le mot de passe provisoire du banc Orion-Test est azur-42."


def front(path):
    """Front matter of a note: every value is written as JSON, which is valid YAML."""
    lines = Path(path).read_text(encoding="utf-8").split("\n")
    assert lines[0] == "---"
    end = lines.index("---", 1)
    return {k: json.loads(v) for k, v in (line.split(": ", 1) for line in lines[1:end])}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = self.root / "store"
        self.memory = PersistentMemory(self.store, "atlas", create=True)
        self.day = self.memory.remember(DAY, source_id="deploy-day")
        self.rule = self.memory.derive(RULE, parents=[self.day["ref"]], artifact_id="freeze-rule")
        self.out = self.root / "vault" / "memoire"

    def tearDown(self):
        self._tmp.cleanup()

    def export(self, **options):
        return export_store(self.store, self.out, **options)

    def note(self, rel):
        return (self.out / rel).read_text(encoding="utf-8")

    def all_text(self):
        return "\n".join(p.read_text(encoding="utf-8") for p in self.out.rglob("*") if p.is_file())


class Notes(Base):
    def test_one_note_per_served_entry_with_provenance_links(self):
        report = self.export()
        self.assertEqual(report["notes"], 2)
        self.assertEqual(sorted(report["written"]), ["atlas/deploy-day.md", "atlas/freeze-rule.md", "atlas/index.md"])
        rule = front(self.out / "atlas/freeze-rule.md")
        self.assertEqual(rule["artifact_id"], "freeze-rule")
        self.assertEqual(rule["version"], self.rule["ref"]["version_id"])
        self.assertEqual((rule["state"], rule["kind"], rule["authority_kind"]), ("active", "procedure", "derived"))
        self.assertEqual(rule["derived_from"], ["[[deploy-day]]"])
        self.assertIn("kind/procedure", rule["tags"])
        body = self.note("atlas/freeze-rule.md")
        self.assertIn("# Geler la branche main le lundi soir", body)
        self.assertIn("Prevenir l'equipe support.", body)
        self.assertIn("- Derived from [[deploy-day|deploy-day]]", body)
        self.assertIn("- Used by [[freeze-rule|freeze-rule]]", self.note("atlas/deploy-day.md"))
        index = self.note("atlas/index.md")
        self.assertIn("2 entries served by the memory", index)
        self.assertIn("[[deploy-day|%s]]" % DAY, index)
        manifest = json.loads((self.out / MANIFEST).read_text())
        self.assertEqual(sorted(manifest["files"]), sorted(report["written"]))

    def test_markdown_style_uses_relative_links(self):
        self.export(style="markdown")
        self.assertIn("- Derived from [deploy-day](<deploy-day.md>)", self.note("atlas/freeze-rule.md"))
        self.assertEqual(front(self.out / "atlas/freeze-rule.md")["derived_from"], ["deploy-day"])
        self.assertNotIn("[[", self.all_text())

    def test_every_workspace_by_default_or_only_the_ones_asked(self):
        other = PersistentMemory(self.store, "orion")
        other.remember("Le banc Orion-Test redemarre a 6 h.", source_id="reboot")
        self.assertEqual(self.export()["workspaces"], ["atlas", "orion"])
        self.assertTrue((self.out / "orion/reboot.md").is_file())
        report = export_store(self.store, self.root / "seul", workspaces=["orion"])
        self.assertEqual(report["workspaces"], ["orion"])
        self.assertFalse((self.root / "seul/atlas").exists())


class FollowsTheMemory(Base):
    def test_second_run_changes_nothing(self):
        self.export()
        before = {p: p.read_bytes() for p in self.out.rglob("*.md")}
        report = self.export()
        self.assertEqual(report["written"], [])
        self.assertEqual(len(report["unchanged"]), 3)
        self.assertEqual({p: p.read_bytes() for p in self.out.rglob("*.md")}, before)

    def test_correction_replaces_the_note_with_the_new_version(self):
        self.export()
        fixed = self.memory.correct("deploy-day", "Les mises en production ont lieu le jeudi.",
                                    expected_version=self.day["ref"]["version_id"])
        report = self.export()
        self.assertIn("atlas/deploy-day.md", report["written"])
        self.assertEqual(front(self.out / "atlas/deploy-day.md")["version"], fixed["ref"]["version_id"])
        self.assertIn("jeudi", self.note("atlas/deploy-day.md"))
        self.assertNotIn("mardi", self.note("atlas/deploy-day.md"))

    def test_withdrawal_removes_the_entry_and_what_derives_from_it(self):
        self.export()
        self.memory.withdraw("deploy-day", "erreur de saisie")
        report = self.export()
        self.assertEqual(sorted(report["removed"]), ["atlas/deploy-day.md", "atlas/freeze-rule.md"])
        self.assertEqual(report["notes"], 0)
        self.assertNotIn("mardi", self.all_text())
        self.assertIn("0 entries served by the memory", self.note("atlas/index.md"))

    def test_withdrawn_entries_on_request_as_notes_without_their_text(self):
        secret = self.memory.remember(SECRET, source_id="orion-secret")
        self.export()
        self.assertIn("azur-42", self.note("atlas/orion-secret.md"))
        self.memory.withdraw("orion-secret", "secret publie par erreur")
        self.export(include_withdrawn=True)
        stub = front(self.out / "atlas/_withdrawn/orion-secret.md")
        self.assertEqual((stub["state"], stub["version"]), ("withdrawn", secret["ref"]["version_id"]))
        self.assertNotIn("azur-42", self.all_text())
        self.assertFalse((self.out / "atlas/orion-secret.md").exists())
        self.assertIn("## Not served (1)", self.note("atlas/index.md"))


class LeavesYourFilesAlone(Base):
    def test_a_note_edited_by_hand_is_kept_until_forced(self):
        self.export()
        edited = self.out / "atlas/deploy-day.md"
        edited.write_text(edited.read_text(encoding="utf-8") + "\nMa remarque.\n", encoding="utf-8")
        self.memory.correct("deploy-day", "Les mises en production ont lieu le jeudi.",
                            expected_version=self.day["ref"]["version_id"])
        report = self.export()
        self.assertEqual(report["kept_edited"], ["atlas/deploy-day.md"])
        self.assertIn("Ma remarque.", edited.read_text(encoding="utf-8"))
        self.assertIn("atlas/deploy-day.md", json.loads((self.out / MANIFEST).read_text())["files"])
        self.assertEqual(self.export()["kept_edited"], ["atlas/deploy-day.md"])
        report = self.export(force=True)
        self.assertIn("atlas/deploy-day.md", report["written"])
        self.assertNotIn("Ma remarque.", edited.read_text(encoding="utf-8"))
        self.assertIn("jeudi", edited.read_text(encoding="utf-8"))

    def test_an_edited_note_is_not_deleted_when_its_entry_goes(self):
        self.export()
        edited = self.out / "atlas/freeze-rule.md"
        edited.write_text("Je garde cette note.\n", encoding="utf-8")
        self.memory.withdraw("deploy-day", "erreur de saisie")
        report = self.export()
        self.assertEqual(report["removed"], ["atlas/deploy-day.md"])
        self.assertEqual(report["kept_edited"], ["atlas/freeze-rule.md"])
        self.assertEqual(edited.read_text(encoding="utf-8"), "Je garde cette note.\n")
        self.assertNotIn("atlas/freeze-rule.md", json.loads((self.out / MANIFEST).read_text())["files"])

    def test_files_the_export_did_not_write_are_never_touched(self):
        self.export()
        mine = self.out / "atlas/mes-notes.md"
        mine.write_text("A moi.\n", encoding="utf-8")
        self.memory.remember("Le banc Orion-Test redemarre a 6 h.", source_id="reboot")
        squatted = self.out / "atlas/reboot.md"
        squatted.write_text("Deja la.\n", encoding="utf-8")
        report = self.export(force=True)
        self.assertEqual(report["kept_foreign"], ["atlas/reboot.md"])
        self.assertEqual(squatted.read_text(encoding="utf-8"), "Deja la.\n")
        self.assertEqual(mine.read_text(encoding="utf-8"), "A moi.\n")
        self.memory.withdraw("deploy-day", "erreur de saisie")
        self.export()
        self.assertTrue(mine.is_file())


class Refusals(Base):
    def assertRefused(self, reason, output=None, **options):
        with self.assertRaises(MemoryError) as caught:
            export_store(self.store, output or self.out, **options)
        self.assertEqual(str(caught.exception), reason)

    def test_a_folder_with_other_content_and_no_manifest(self):
        self.out.mkdir(parents=True)
        (self.out / "journal.md").write_text("x\n", encoding="utf-8")
        self.assertRefused("export_target_not_empty")
        self.assertEqual([p.name for p in self.out.iterdir()], ["journal.md"])

    def test_inside_the_store_or_a_missing_store_or_a_bad_style(self):
        self.assertRefused("export_inside_store", output=self.store / "notes")
        self.assertRefused("invalid_export_style", style="html")
        with self.assertRaises(MemoryError) as caught:
            export_store(self.root / "nulle-part", self.out)
        self.assertEqual(str(caught.exception), "store_missing")

    def test_a_manifest_pointing_outside_deletes_nothing(self):
        self.export()
        outside = self.root / "vault" / "precieux.md"
        outside.write_text("Ne pas effacer.\n", encoding="utf-8")
        manifest = json.loads((self.out / MANIFEST).read_text())
        manifest["files"]["../precieux.md"] = "0" * 64
        (self.out / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        self.assertRefused("export_manifest_unreadable")
        self.assertTrue(outside.is_file())
        (self.out / MANIFEST).write_text("{pas du json", encoding="utf-8")
        self.assertRefused("export_manifest_unreadable")

    def test_a_linked_folder_that_leads_outside(self):
        elsewhere = self.root / "ailleurs"
        elsewhere.mkdir()
        self.out.mkdir(parents=True)
        try:
            (self.out / "atlas").symlink_to(elsewhere, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:  # Windows without the symlink privilege
            self.skipTest("cannot create a folder link here: %s" % exc)
        manifest = {"schema": "persistent-memory.export.v1", "files": {}}
        (self.out / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        self.assertRefused("export_path_escapes")
        self.assertEqual(list(elsewhere.iterdir()), [])


class Names(Base):
    def test_unsafe_reserved_and_colliding_ids_get_distinct_safe_names(self):
        ids = ["a/b", "CON", "Deploy-Day", "index", "ok:ou?pas*", "x" * 140]
        for n, artifact_id in enumerate(ids):
            self.memory.remember("Entree numero %d." % n, source_id=artifact_id)
        self.export()
        names = sorted(p.relative_to(self.out).as_posix() for p in self.out.rglob("*.md"))
        self.assertEqual(len(names), len(ids) + 3)
        self.assertEqual(len({n.lower() for n in names}), len(names))
        for name in names:
            stem = name.split("/")[-1][:-3]
            self.assertLessEqual(len(stem), 110)
            self.assertNotRegex(stem, r'[<>:"/\\|?*\[\]#^]')
            self.assertNotIn(stem.upper(), {"CON", "PRN", "AUX", "NUL"})
        self.assertFalse((self.out / "atlas/deploy-day.md").exists())  # Deploy-Day and deploy-day: both suffixed
        self.assertEqual(sum(1 for n in names if n.endswith("/index.md")), 1)
        by_id = {front(self.out / n)["artifact_id"]: n for n in names if not n.endswith("/index.md")}
        self.assertEqual(sorted(by_id), sorted(ids + ["deploy-day", "freeze-rule"]))

    def test_names_do_not_depend_on_the_order_entries_arrive(self):
        self.memory.remember("Premier.", source_id="Release")
        self.memory.remember("Second.", source_id="release")
        self.export()
        first = sorted(p.name for p in (self.out / "atlas").iterdir())
        other = Base()
        other.setUp()
        try:
            other.memory.remember("Second.", source_id="release")
            other.memory.remember("Premier.", source_id="Release")
            other.export()
            self.assertEqual(sorted(p.name for p in (other.out / "atlas").iterdir()), first)
        finally:
            other.tearDown()


class Command(Base):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["export", str(self.out), "--store", str(self.store), *args])
        return code, out.getvalue(), err.getvalue()

    def test_exit_codes_and_json(self):
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("2 notes in", out)
        code, out, _ = self.run_cli("--json", "--style", "obsidian")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["unchanged"]), 3)
        (self.out / "atlas/deploy-day.md").write_text("edite\n", encoding="utf-8")
        self.memory.correct("deploy-day", "Les mises en production ont lieu le jeudi.",
                            expected_version=self.day["ref"]["version_id"])
        code, out, _ = self.run_cli()
        self.assertEqual(code, 3)
        self.assertIn("atlas/deploy-day.md", out)
        code, _, err = self.run_cli("--workspace", "atlas", "--style", "markdown", "--force")
        self.assertEqual(code, 0)
        (self.out / MANIFEST).write_text("{", encoding="utf-8")
        code, _, err = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn("export_manifest_unreadable", err)


if __name__ == "__main__":
    unittest.main()
