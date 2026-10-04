"""Product-specific tests; separate from inherited core/retrieval contracts."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hermes_memory import Authority, Memory
from hermes_memory.demo import run
from hermes_memory.typed_facade import Facade, Policy
from hermes_memory.typed_memory_tool import execute_tool, with_tool


class ProductTests(unittest.TestCase):
    def test_two_actor_restart_and_restore_example(self):
        with tempfile.TemporaryDirectory() as root:
            result = run(Path(root) / 'example')
        for key in ['restart_read_allowed', 'withdrawn_source_denied', 'dependent_handoff_denied',
                    'old_content_restore_quarantined', 'control_source_preserved']:
            self.assertTrue(result[key], key)

    def test_example_refuses_existing_directory(self):
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / 'keep.txt'
            marker.write_text('synthetic control')
            with self.assertRaises(FileExistsError):
                run(root)
            self.assertEqual(marker.read_text(), 'synthetic control')

    def test_generic_tool_registration_idempotence_and_structured_result(self):
        class StubClient:
            def context(self, arguments):
                return {'status': 'completed', 'context': arguments['query'], 'items': []}
        with patch.dict(os.environ, {'HERMES_TYPED_MEMORY_ENABLED': '1'}):
            tools = with_tool([])
            self.assertEqual(with_tool(tools), tools)
            result = asyncio.run(execute_tool({'query': 'synthetic query'}, client=StubClient()))
        self.assertTrue(result['success'])
        self.assertEqual(result['result']['context'], 'synthetic query')

    def test_context_cli_uses_installed_package_and_explicit_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            authority = Authority.create(root / 'authority.db', root / 'anchor.json')
            memory = Memory.create(root / 'content.db', authority)
            policy = Policy(enabled=True)
            facade = Facade(memory, root / 'index.db', policy)
            request = {'schema_version': 1, 'policy_id': policy.policy_id}
            ref = facade.admit_source({**request, 'source_id': 'A', 'text': 'Synthetic copper context.',
                                       'metadata': {}, 'expected_version': None})['ref']
            facade.sync(request)
            config = root / 'policy.json'
            config.write_text(json.dumps({'enabled': True}))
            query = root / 'query.json'
            query.write_text(json.dumps({**request, 'query': 'copper'}))
            command = [sys.executable, '-m', 'hermes_memory.typed_admin', '--authority', str(authority.path),
                       '--anchor', str(authority.anchor_path), '--store', str(memory.path), '--index',
                       str(facade.index_path), '--config', str(config), 'context', '--request', str(query)]
            result = subprocess.run(command, text=True, capture_output=True, timeout=10, cwd=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(result.stdout)
            self.assertEqual(value['items'][0]['ref'], ref)
            self.assertEqual(value['context'], 'Synthetic copper context.')


if __name__ == '__main__':
    unittest.main()
