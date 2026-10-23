"""Product-specific tests; separate from inherited core/retrieval contracts."""
import asyncio
import copy
import hashlib
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
    def test_benchmark_cli_rejects_out_of_contract_and_ambiguous_modes(self):
        benchmark = Path(__file__).resolve().parents[1] / 'benchmarks/run_benchmark.py'
        for arguments in (['--documents', '0'], ['--documents', '5001'],
                          ['--repetitions', '0'], ['--repetitions', '100001'],
                          ['--seed', '-1'], ['--seed', str(2 ** 64)],
                          ['--lance-hybrid', '--documents', '24'],
                          ['--lance-hybrid', '--repetitions', '10'],
                          ['--lance-hybrid', '--seed', '0'],
                          ['--compare-transitions', '--documents', '3'],
                          ['--compare-transitions', '--trajectories', '3'],
                          ['--compare-transitions', '--lance-hybrid'],
                          ['--compare-transitions', '--variants', '0'],
                          ['--compare-transitions', '--variants', '11'],
                          ['--compare-transitions', '--seed', '-1'],
                          ['--variants', '1'], ['--comparison-fixture', 'unused.json']):
            with self.subTest(arguments=arguments):
                result = subprocess.run([sys.executable, str(benchmark), *arguments],
                                        text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, '')

    def test_benchmark_default_and_seeded_retrieval_oracle(self):
        benchmark = Path(__file__).resolve().parents[1] / 'benchmarks/run_benchmark.py'
        baseline = subprocess.run([sys.executable, str(benchmark)],
                                  text=True, capture_output=True, timeout=20)
        self.assertEqual(baseline.returncode, 0, baseline.stderr)
        default = json.loads(baseline.stdout)
        self.assertEqual(default['synthetic_documents'], 24)
        self.assertEqual(default['repetitions'], 10)
        self.assertEqual(set(default), {'synthetic_documents', 'repetitions', 'median_seconds',
                                       'max_seconds', 'revocation_checked', 'cold_cache_controlled',
                                       'general_speed_superiority_claimed'})
        reports = []
        for _ in range(2):
            result = subprocess.run([sys.executable, str(benchmark), '--documents', '3',
                                     '--repetitions', '7', '--seed', '5'],
                                    text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            reports.append(json.loads(result.stdout))
        for report in reports:
            self.assertTrue(report['oracle_passed'])
            self.assertEqual(report['expected_hits'], 7)
            self.assertEqual(report['omissions'], 0)
            self.assertEqual(report['unexpected_items'], 0)
            self.assertEqual(report['candidate_truncated_queries'], 0)
            self.assertEqual(report['status_counts'], {'completed': 7})
            self.assertEqual(report['public_method_calls_total'], 22)
            self.assertEqual(report['public_method_calls']['typed.search'], 9)
            self.assertEqual(report['public_method_calls']['memory.read'], 7)
            self.assertEqual(report['API_calls_requested_by_benchmark'], 0)
            self.assertFalse(report['cold_cache_controlled'])
            self.assertFalse(report['ranking_quality_evaluated'])
        self.assertEqual(reports[0]['query_schedule_sha256'], reports[1]['query_schedule_sha256'])
        self.assertLessEqual(reports[0]['distinct_queries'], 3)

    @staticmethod
    def _efficiency_inputs():
        module, folder = ProductTests._lifecycle_benchmark()
        manifest_path = folder / 'efficiency-20261023/INPUTS.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        inputs = {name: json.loads((manifest_path.parent / ref['path']).read_text(encoding='utf-8'))
                  for name, ref in manifest['inputs'].items()}
        return module, manifest_path, manifest, inputs

    def test_efficiency_preserves_quality_and_separates_reasoning_and_cost_scope(self):
        module, _, manifest, inputs = self._efficiency_inputs()
        original = copy.deepcopy(inputs)
        report = module.calculate_efficiency(inputs['generations'], inputs['report'], manifest['historical_prices'])
        self.assertEqual(inputs, original)
        self.assertEqual(report['usage_coverage'], 1500)
        self.assertEqual(len(report['episodes']), 1500)
        self.assertEqual(len(report['groups']), 5)
        self.assertEqual(report['provider_requests'], 0)
        self.assertEqual(report['new_judgments'], 0)
        self.assertTrue(report['post_hoc'])
        self.assertTrue(report['exploratory'])
        self.assertIsNone(report['actual_billed_usd'])
        self.assertFalse(report['limits']['quality_noninferiority_confirmed'])
        self.assertFalse(report['limits']['dominance_claimed'])
        self.assertEqual(report['estimated_generation_usd'], '0.7040665')
        groups = {(row['model'], row['arm']): row for row in report['groups']}
        self.assertEqual(groups[('gpt-6-luna', 'memory_on')]['successes'], 298)
        self.assertEqual(groups[('gpt-6-luna', 'simple_baseline')]['successes'], 294)
        self.assertEqual(groups[('gpt-6.1-sol', 'memory_off')]['observed']['reasoning_tokens'], 33)
        self.assertEqual(groups[('gpt-6.1-sol', 'memory_on')]['observed']['reasoning_tokens'], 9)
        for row in report['groups']:
            self.assertEqual(row['answers'], 300)
            self.assertEqual(row['scenario_groups'], 100)
            self.assertEqual(row['observed']['total_tokens'],
                             row['observed']['prompt_tokens'] + row['observed']['completion_tokens'])
            self.assertEqual(row['observed']['cached_tokens'], 0)
        comparisons = report['paired_comparisons']
        self.assertEqual(len(comparisons), 3)
        self.assertEqual(sum(row['paired_responses'] for row in comparisons), 900)
        lexical = comparisons[1]
        self.assertEqual(lexical['observed_deltas_a_minus_b']['total_tokens']['sum_difference'], -5829)
        self.assertEqual(lexical['observed_deltas_a_minus_b']['context_chars']['sum_difference'], -4653)
        self.assertEqual(lexical['observed_deltas_a_minus_b']['estimated_generation_usd']['sum_difference'], '-0.0007325')
        self.assertEqual(lexical['frozen_quality_statistics']['effect_uncertainty_interval_95'],
                         inputs['report']['secondary_comparisons'][0]['statistics']['effect_uncertainty_interval_95'])

    def test_efficiency_rejects_incomplete_and_misbound_observations(self):
        module, _, manifest, inputs = self._efficiency_inputs()
        for mutation in ('missing_usage', 'boolean_tokens', 'negative_tokens', 'total_mismatch',
                         'missing_details', 'cache_overflow', 'cached_without_tariff', 'reasoning_overflow',
                         'missing_generation', 'duplicate_quality', 'missing_quality', 'wrong_case',
                         'wrong_cell_id', 'wrong_repetition', 'wrong_model', 'wrong_policy', 'unknown_quality',
                         'changed_body', 'missing_group', 'usage_aggregate', 'quality_aggregate'):
            changed = copy.deepcopy(inputs)
            rows = changed['generations']['results']
            cell_id = next(iter(rows))
            row = rows[cell_id]
            q = next(item for item in changed['report']['episodes'] if item['cell_id'] == cell_id)
            if mutation == 'missing_usage':
                del row['usage']
            elif mutation == 'boolean_tokens':
                row['usage']['prompt_tokens'] = True
            elif mutation == 'negative_tokens':
                row['usage']['prompt_tokens'] = -1
            elif mutation == 'total_mismatch':
                row['usage']['total_tokens'] += 1
            elif mutation == 'missing_details':
                del row['usage']['completion_tokens_details']['reasoning_tokens']
            elif mutation == 'cache_overflow':
                row['usage']['prompt_tokens_details']['cached_tokens'] = row['usage']['prompt_tokens'] + 1
            elif mutation == 'cached_without_tariff':
                row['usage']['prompt_tokens_details']['cached_tokens'] = 1
            elif mutation == 'reasoning_overflow':
                row['usage']['completion_tokens_details']['reasoning_tokens'] = row['usage']['completion_tokens'] + 1
            elif mutation == 'missing_generation':
                del rows[cell_id]
            elif mutation == 'duplicate_quality':
                changed['report']['episodes'][0] = copy.deepcopy(changed['report']['episodes'][1])
            elif mutation == 'missing_quality':
                changed['report']['episodes'].pop()
            elif mutation == 'wrong_case':
                row['case_id'] = 'V22-F10-G10-T01'
            elif mutation == 'wrong_cell_id':
                row['cell_id'] = 'V22-L-misbound-R1-LEX'
            elif mutation == 'wrong_repetition':
                row['repetition'] = 1
            elif mutation == 'wrong_model':
                row['response_model'] = 'gpt-6.1-sol'
            elif mutation == 'wrong_policy':
                row['policy_id'] = 'no_memory'
            elif mutation == 'unknown_quality':
                q['success'] = None
            elif mutation == 'changed_body':
                row['body'] += ' changed'
            elif mutation == 'missing_group':
                changed['report']['primary']['tasks'][0]['scenario_group'] = 'other'
            elif mutation == 'usage_aggregate':
                changed['report']['latencies_and_usage'][0]['observed_tokens']['prompt_tokens'] += 1
            else:
                changed['report']['by_model_arm'][0]['success'] += 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                module.calculate_efficiency(changed['generations'], changed['report'], manifest['historical_prices'])

    def test_efficiency_rejects_invalid_or_changed_historical_prices(self):
        module, _, manifest, inputs = self._efficiency_inputs()
        for price in ('NaN', 'Infinity', '-0.1', '0', '0.11', 0.1, True, None):
            changed = copy.deepcopy(manifest['historical_prices'])
            changed['USD_per_million']['gpt-6-luna']['input'] = price
            with self.subTest(price=price), self.assertRaises(ValueError):
                module.calculate_efficiency(inputs['generations'], inputs['report'], changed)

    def test_efficiency_cli_isolated_offline_and_manifest_pins(self):
        module, manifest_path, _, _ = self._efficiency_inputs()
        benchmark = manifest_path.parent.parent / 'run_benchmark.py'
        for custom in (False, True):
            arguments = ['--efficiency']
            if custom:
                arguments += ['--efficiency-inputs', str(manifest_path),
                              '--efficiency-inputs-sha256', module.EFFICIENCY_INPUTS_SHA256]
            result = subprocess.run([sys.executable, '-I', str(benchmark), *arguments],
                                    text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['mode'], 'frozen_paired_efficiency_v1')
            self.assertEqual(report['provenance']['inputs_manifest_sha256'], module.EFFICIENCY_INPUTS_SHA256)
            self.assertEqual(report['usage_missing'], 0)
            self.assertEqual(report['estimated_generation_usd'], '0.7040665')
        for arguments in (['--efficiency', '--documents', '1'], ['--efficiency', '--seed', '0'],
                          ['--efficiency', '--trajectories', '1'], ['--efficiency', '--compare-transitions'],
                          ['--efficiency', '--lance-hybrid'], ['--efficiency-inputs', str(manifest_path)],
                          ['--efficiency', '--efficiency-inputs', str(manifest_path)],
                          ['--efficiency', '--efficiency-inputs-sha256', '0' * 64]):
            with self.subTest(arguments=arguments):
                result = subprocess.run([sys.executable, '-I', str(benchmark), *arguments],
                                        text=True, capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, '')
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'benchmarks' / 'efficiency'
            folder.mkdir(parents=True)
            duplicate = b'{"post_hoc":true,"post_hoc":true}'
            bad_manifest = folder / 'INPUTS.json'
            bad_manifest.write_bytes(duplicate)
            with self.assertRaisesRegex(ValueError, 'duplicate_json_key'):
                module.efficiency_analysis(bad_manifest, hashlib.sha256(duplicate).hexdigest(), emit=False)

    @staticmethod
    def _lifecycle_benchmark():
        benchmark = Path(__file__).resolve().parents[1] / 'benchmarks' / 'run_benchmark.py'
        spec = importlib.util.spec_from_file_location('product_lifecycle_benchmark', benchmark)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module, benchmark.parent

    def test_lifecycle_matched_arms_and_arm_order_independence(self):
        module, folder = self._lifecycle_benchmark()
        with patch.object(sys, 'path', [str(folder), *sys.path]):
            first = module.compare_transitions(variants=1, emit=False)
            reverse = module.compare_transitions(variants=1, arm_order=tuple(reversed(module.COMPARISON_ARMS)), emit=False)
        self.assertEqual(first['seed'], 20261022)
        self.assertEqual(first['cases_per_arm'], 10)
        self.assertEqual(first['provider_requests'], 0)
        self.assertTrue(first['oracle_passed'])
        self.assertTrue(first['profile_conformance_passed'])
        self.assertEqual(first['schedule_sha256'], reverse['schedule_sha256'])
        self.assertEqual(first['case_order'], reverse['case_order'])
        for arm in module.COMPARISON_ARMS:
            self.assertEqual(first['arms'][arm]['counts'], reverse['arms'][arm]['counts'])
            self.assertEqual(first['arms'][arm]['deterministic_observations_sha256'],
                             reverse['arms'][arm]['deterministic_observations_sha256'])
            self.assertEqual(first['arms'][arm]['counts']['unexpected_errors'], 0)
            self.assertEqual(first['arms'][arm]['counts']['completed_cases'], 10)
        for arm in ('hermes', 'sqlite_retained'):
            counts = first['arms'][arm]['counts']
            self.assertEqual(counts['forbidden_reads_exposed'], 0)
            self.assertEqual(counts['valid_reads_unavailable'], 0)
            self.assertEqual(counts['valid_reads_wrong_content'], 0)
            self.assertEqual(counts['forbidden_writes_accepted'], 0)
            self.assertGreater(counts['valid_reads_exact'], 0)
            self.assertEqual(counts['expected_rejections'], counts['matched_rejections'])
            self.assertGreater(counts['idempotence_checks'], 0)
        local = first['arms']['sqlite_snapshot_local']['counts']
        self.assertGreater(local['forbidden_reads_exposed'], 0)
        self.assertEqual(local['profile_passed_cases'], 10)

    def test_lifecycle_comparison_cli_works_in_isolated_python(self):
        benchmark = Path(__file__).resolve().parents[1] / 'benchmarks/run_benchmark.py'
        result = subprocess.run([sys.executable, '-I', str(benchmark), '--compare-transitions',
                                 '--variants', '1'], text=True, capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['mode'], 'matched_lifecycle_transitions_v1')
        self.assertEqual(report['cases_per_arm'], 10)
        self.assertTrue(report['oracle_passed'])
        self.assertTrue(report['profile_conformance_passed'])

    def test_lifecycle_external_oracle_and_block_all_mutations_fail(self):
        module, folder = self._lifecycle_benchmark()
        fixture = json.loads((folder / 'lifecycle-20261022/FIXTURE.json').read_text(encoding='utf-8'))
        case = next(c for c in module.comparison_schedule(fixture, 1) if c['scenario'] == 'Q01')
        with patch.object(sys, 'path', [str(folder), *sys.path]):
            support = module._comparison_support()
            HermesAdapter, SQLiteReference = support.HermesAdapter, support.SQLiteReference
            with tempfile.TemporaryDirectory() as directory:
                backend = HermesAdapter(Path(directory))
                with patch.object(backend, 'read', return_value={'allowed': False, 'reason': 'blocked'}):
                    result = module.replay_comparison_case(backend, case, 'retained_authority')
                self.assertFalse(result['oracle_passed'])
                counts = module.summarize_comparison([result])
                self.assertGreater(counts['valid_reads_unavailable'], 0)
            changed = copy.deepcopy(case)
            read = next(op for op in changed['operations'] if op['op'] == 'read')
            read['expect']['text'] = read['expect']['text'].replace('—', '-')
            with tempfile.TemporaryDirectory() as directory:
                result = module.replay_comparison_case(HermesAdapter(Path(directory)), changed, 'retained_authority')
            self.assertFalse(result['oracle_passed'])
            self.assertEqual(module.summarize_comparison([result])['valid_reads_wrong_content'], 1)
            denied_case = next(c for c in module.comparison_schedule(fixture, 1) if c['scenario'] == 'Q03')
            with tempfile.TemporaryDirectory() as directory:
                backend = SQLiteReference(Path(directory))
                with patch.object(backend, 'read', return_value={'allowed': False, 'content': 'synthetic forbidden body'}):
                    result = module.replay_comparison_case(backend, denied_case, 'retained_authority')
            self.assertFalse(result['oracle_passed'])
            self.assertGreater(module.summarize_comparison([result])['forbidden_reads_exposed'], 0)

    def test_lifecycle_unexpected_errors_and_content_on_denial_are_not_passes(self):
        module, folder = self._lifecycle_benchmark()
        with patch.object(sys, 'path', [str(folder), *sys.path]):
            from hermes_memory.core import MemoryError
            import sqlite3
            self.assertEqual(module.normalize_lifecycle_rejection(MemoryError('version_not_current')), 'dependency_invalid')
            self.assertIsNone(module.normalize_lifecycle_rejection(sqlite3.OperationalError('version_conflict')))
            self.assertIsNone(module.normalize_lifecycle_rejection(ValueError('version_conflict')))
            class Broken:
                def put_source(self, *args):
                    raise sqlite3.OperationalError('version_conflict')
            case = {'case_id': 'negative', 'scenario': 'Q05', 'variant': 'negative', 'operations': [
                {'op': 'source', 'as': 'A', 'workspace': 'synthetic', 'id': 'A', 'text': 'x', 'expect_error': 'version_conflict'},
                {'op': 'reopen'}]}
            result = module.replay_comparison_case(Broken(), case, 'retained_authority')
            self.assertFalse(result['oracle_passed'])
            self.assertFalse(result['completed'])
            counts = module.summarize_comparison([result])
            self.assertEqual(counts['unexpected_errors'], 1)
            self.assertEqual(counts['unexecuted_operations'], 1)
        self.assertFalse(module._comparison_read_matches({'allowed': False, 'content': 'leak'},
                                                       {'allowed': False, 'text_absent': True}))

    def test_lifecycle_fixture_and_schedule_reject_unknown_or_incomplete_oracles(self):
        module, folder = self._lifecycle_benchmark()
        fixture = json.loads((folder / 'lifecycle-20261022/FIXTURE.json').read_text(encoding='utf-8'))
        first = module.comparison_schedule(fixture, 1)
        self.assertEqual(first, module.comparison_schedule(fixture, 1))
        self.assertEqual(len(first), 10)
        for mutation in ('unknown_op', 'missing_text'):
            changed = copy.deepcopy(fixture)
            operations = changed['scenarios'][0]['variants'][0]['operations']
            if mutation == 'unknown_op':
                operations[0]['op'] = 'silently_ignore'
            else:
                del next(op for op in operations if op['op'] == 'read')['expect']['text']
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                module.comparison_schedule(changed, 1)

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
