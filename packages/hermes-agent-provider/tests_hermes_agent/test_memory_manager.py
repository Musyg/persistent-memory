"""Integration test through Hermes Agent's own MemoryManager.

Run it from a Hermes Agent checkout's environment:
    python -m unittest discover -s packages/hermes-agent-provider/tests_hermes_agent
Without Hermes Agent it is reported as SKIPPED with its reason, never as passed. It is kept
out of ``tests/`` because this repository's installed-distribution check counts a skip as a failure.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock

try:
    from agent.memory_manager import MemoryManager
except ImportError as exc:  # pragma: no cover - depends on the environment
    MemoryManager = None
    MISSING = f"Hermes Agent is not importable here ({exc})"
else:
    MISSING = ""

from hermes_agent_provenance import HERMES_AGENT_AVAILABLE, ProvenanceMemoryProvider


@unittest.skipIf(MemoryManager is None, MISSING)
class HermesMemoryManagerTests(unittest.TestCase):
    def test_provider_runs_on_hermes_base_class(self):
        self.assertTrue(HERMES_AGENT_AVAILABLE)

    def test_remember_recall_withdraw_through_the_manager(self):
        with tempfile.TemporaryDirectory(prefix="hermes-agent-provenance-") as home, \
                mock.patch.dict(os.environ, {"HERMES_HOME": home}):
            # The manager refuses tool calls from a profile other than the one the provider is bound to.
            manager = MemoryManager()
            manager.add_provider(ProvenanceMemoryProvider())
            manager.initialize_all(session_id="mm", hermes_home=home, platform="cli")
            stored = json.loads(manager.handle_tool_call(
                "provenance_remember", {"text": "Orion-Test utilise le port 9300."}))
            source_id = stored["source_id"]
            self.assertIn(source_id, manager.prefetch_all("Quel port utilise Orion-Test ?", session_id="mm"))
            manager.handle_tool_call("provenance_withdraw", {"source_id": source_id, "reason": "obsolete"})
            merged = manager.prefetch_all("Quel port utilise Orion-Test ?", session_id="mm")
            self.assertIn("Withdrawn sources", merged)
            self.assertNotIn("9300", merged)


if __name__ == "__main__":
    unittest.main()
