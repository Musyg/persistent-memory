import json
from pathlib import Path
import tempfile
import unittest

from hermes_policy_registry.demo import run


class PublicDemoTests(unittest.TestCase):
    def test_synthetic_proposal_admission_reopen_and_source_withdrawal(self):
        with tempfile.TemporaryDirectory() as temp:
            result = run(Path(temp) / 'new-demo')
            self.assertEqual(result['state_before_withdrawal'], 'admitted')
            self.assertEqual(result['state_after_withdrawal'], 'rollback')
            self.assertFalse(result['runtime_activated'])
            self.assertFalse(result['measured_performance'])
            self.assertEqual((result['provider_calls'], result['retrieval_calls']), (0, 0))
            self.assertEqual(result['data_class'], 'synthetic_demo_not_measurement')
            self.assertEqual(len(result['record_refs']), 2)

    def test_existing_path_refused_without_overwriting_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'demo'
            run(path)
            before = {p.name: p.read_bytes() for p in path.iterdir() if p.is_file()}
            with self.assertRaises(FileExistsError):
                run(path)
            self.assertEqual(before, {p.name: p.read_bytes() for p in path.iterdir() if p.is_file()})


if __name__ == '__main__':
    unittest.main()
