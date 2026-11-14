"""Provider contract tests. They need hermes-memory-core, not Hermes Agent."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest

import hermes_agent_provenance as hap
from hermes_agent_provenance import ProvenanceMemoryProvider, load_config, report

PORT = "Le serveur Orion-Test ecoute sur le port 9300."
COLOR = "La couleur de la marque Orion-Test est le vert sapin."


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="hermes-agent-provenance-")
        self.home = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def make(self, session="s1", **kwargs):
        provider = ProvenanceMemoryProvider()
        provider.initialize(session, hermes_home=self.home, platform="cli", **kwargs)
        return provider

    @staticmethod
    def call(provider, tool, **args):
        return json.loads(provider.handle_tool_call(tool, args))

    def remember(self, provider, text, kind="observation"):
        out = self.call(provider, "provenance_remember", text=text, kind=kind)
        self.assertIn("source_id", out, out)
        return out["source_id"]

    def test_provider_uses_the_active_base_class(self):
        self.assertTrue(issubclass(ProvenanceMemoryProvider, hap.MemoryProvider))
        self.assertTrue(ProvenanceMemoryProvider().is_available())

    def test_remember_then_search_returns_the_source(self):
        p = self.make()
        sid = self.remember(p, PORT)
        out = self.call(p, "provenance_search", query="Orion-Test port")
        self.assertEqual([r["source_id"] for r in out["results"]], [sid])
        self.assertIn("9300", out["results"][0]["text"])

    def test_prefetch_injects_validated_items_with_source_id(self):
        p = self.make()
        sid = self.remember(p, COLOR)
        block = p.prefetch("Quelle est la couleur de la marque Orion-Test ?", session_id="s1")
        self.assertIn(f"[{sid}]", block)
        self.assertIn("vert sapin", block)
        self.assertEqual(p.recall_status().count, 1)

    def test_withdrawn_source_is_gone_and_session_gets_one_notice(self):
        p = self.make()
        port = self.remember(p, PORT)
        color = self.remember(p, COLOR)
        self.assertIn("9300", p.prefetch("Sur quel port ecoute Orion-Test ?", session_id="s1"))

        out = self.call(p, "provenance_withdraw", source_id=port, reason="port change")
        self.assertIs(out["covered_reads_blocked"], True)

        block = p.prefetch("Sur quel port ecoute Orion-Test ?", session_id="s1")
        self.assertIn("Withdrawn sources", block)
        self.assertIn(f"[{port}]", block)
        self.assertNotIn("9300", block)
        found = self.call(p, "provenance_search", query="port 9300 Orion-Test")["results"]
        self.assertTrue(all(r["source_id"] != port for r in found))

        again = p.prefetch("Et la couleur de la marque Orion-Test ?", session_id="s1")
        self.assertNotIn("Withdrawn sources", again, "a session is warned once per withdrawn source")
        self.assertIn(f"[{color}]", again)

    def test_notice_is_scoped_to_sessions_that_saw_the_source(self):
        p = self.make()
        port = self.remember(p, PORT)
        p.prefetch("port Orion-Test", session_id="saw-it")
        self.call(p, "provenance_withdraw", source_id=port, reason="obsolete")
        self.assertNotIn("Withdrawn sources", p.prefetch("port Orion-Test", session_id="never-saw-it"))
        self.assertIn("Withdrawn sources", p.prefetch("port Orion-Test", session_id="saw-it"))

    def test_tool_search_also_counts_as_exposure(self):
        p = self.make(session="tool-session")
        port = self.remember(p, PORT)
        self.call(p, "provenance_search", query="Orion-Test port")
        self.call(p, "provenance_withdraw", source_id=port, reason="obsolete")
        self.assertIn(f"[{port}]", p.prefetch("merci pour le port", session_id="tool-session"))

    def test_exposure_report_and_cli_exit_code(self):
        p = self.make()
        port = self.remember(p, PORT)
        p.prefetch("port Orion-Test", session_id="s1")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(report.main(["--home", self.home]), 0)
        self.call(p, "provenance_withdraw", source_id=port, reason="obsolete")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(report.main(["--home", self.home]), 1)
        exposed = json.loads(out.getvalue())["exposed_sessions"]
        self.assertEqual(exposed[0]["session_id"], "s1")
        self.assertEqual(exposed[0]["withdrawn_sources"][0]["ref"]["artifact_id"], port)

    def test_report_without_store_is_an_error(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(report.main(["--home", self.home]), 2)

    def test_subagent_cannot_write(self):
        p = self.make(agent_context="subagent")
        self.assertEqual({t["name"] for t in p.get_tool_schemas()}, {"provenance_search", "provenance_explain"})
        self.assertIn("error", self.call(p, "provenance_remember", text="x"))

    def test_withdraw_unknown_source_is_an_error(self):
        p = self.make()
        out = self.call(p, "provenance_withdraw", source_id="m-doesnotexist", reason="x")
        self.assertEqual(out["error"], "unknown_source")

    def test_withdraw_can_be_disabled(self):
        self.make().save_config({"allow_withdraw": "false"}, self.home)
        p = self.make()
        self.assertNotIn("provenance_withdraw", {t["name"] for t in p.get_tool_schemas()})
        self.assertEqual(load_config(self.home)["allow_withdraw"], "false")

    def test_explain_returns_metadata_without_content(self):
        p = self.make()
        sid = self.remember(p, "Secret interne: code 4242.")
        out = self.call(p, "provenance_explain", source_id=sid)
        self.assertEqual(out["source_id"], sid)
        self.assertNotIn("4242", json.dumps(out))

    def test_store_survives_reopen(self):
        sid = self.remember(self.make(), PORT)
        reopened = self.make(session="s2")
        found = self.call(reopened, "provenance_search", query="Orion-Test")["results"]
        self.assertEqual([r["source_id"] for r in found], [sid])

    def test_stale_index_after_external_write_is_rebuilt(self):
        p = self.make()
        self.remember(p, COLOR)
        # Another writer admits a source through the library alone and does not rebuild the index.
        p._store.typed.put("hermes", "external-port", PORT, {"evidence_kind": "document"})
        p._store.memory.drain_outbox()
        found = self.call(p, "provenance_search", query="port Orion-Test")["results"]
        self.assertIn("external-port", [r["source_id"] for r in found])

    def test_sync_turn_stores_nothing(self):
        p = self.make()
        p.sync_turn("Le port est 9300", "Note.", session_id="s1")
        self.assertEqual(self.call(p, "provenance_search", query="port 9300")["results"], [])


if __name__ == "__main__":
    unittest.main()
