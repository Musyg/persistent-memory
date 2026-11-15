"""The provider inside Hermes Agent's own MemoryManager.

Run from a Hermes Agent environment with this package installed:
    python -m unittest discover -s tests_integration
Without Hermes Agent it is reported as SKIPPED with its reason, never as passed.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

try:
    from agent.memory_manager import MemoryManager
except ImportError as exc:  # pragma: no cover - depends on the environment
    MemoryManager = None
    MISSING = "Hermes Agent is not importable here (%s)" % exc
else:
    MISSING = ""

from hermes_memory.hermes_agent import HERMES_AGENT_AVAILABLE, PersistentMemoryProvider


@unittest.skipIf(MemoryManager is None, MISSING)
class HermesMemoryManager(unittest.TestCase):
    def test_runs_on_the_real_base_class(self):
        self.assertTrue(HERMES_AGENT_AVAILABLE)

    def test_entry_point_is_discovered(self):
        from plugins.memory import discover_memory_providers
        self.assertIn("persistent-memory", [entry[0] for entry in discover_memory_providers()])

    def test_remember_recall_withdraw_through_the_manager(self):
        with tempfile.TemporaryDirectory(prefix="pm-hermes-") as home, \
                mock.patch.dict(os.environ, {"HERMES_HOME": home}):
            manager = MemoryManager()
            manager.add_provider(PersistentMemoryProvider())
            manager.initialize_all(session_id="mm", hermes_home=home, platform="cli")
            stored = json.loads(manager.handle_tool_call(
                "memory_remember", {"text": "Orion-Test utilise le port 9300.", "source_id": "port"}))
            self.assertEqual(stored["artifact_id"], "port")
            self.assertIn("[port]", manager.prefetch_all("Quel port utilise Orion-Test ?", session_id="mm"))
            manager.handle_tool_call("memory_withdraw", {"artifact_id": "port", "reason": "obsolete"})
            merged = manager.prefetch_all("Quel port utilise Orion-Test ?", session_id="mm")
            self.assertNotIn("9300", merged)


if __name__ == "__main__":
    unittest.main()
