"""Independent deterministic oracle checks; UNIT examples are not model results.

Linux execution only. No provider, consumer or Memory imports. Sealed layout
checks run only after support/prompt freeze; do not disclose fixture values.
"""
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def unit_cases():
    # Explicit, public synthetic UNIT values; none are sampled fixture params.
    a = {
        'I': {'identifiers': ['0012', '12']},
        'B': {'threshold': 7, 'values': [7]},
        'S': {'entries': [{'kind': 'debit', 'magnitude': 9}]},
        'T': {'primary': {'key': 'k', 'revision': 2, 'value': 'p'},
              'secondary': {'key': 'k', 'revision': 2, 'value': 's'}},
        'C': {'rows': [['unit']], 'csv': {'columns': ['probe'], 'delimiter': ';'}},
        'R': {'record': {'signed': True, 'sealed': False}},
    }
    b = {
        'I': {'rows': [{'identifier': '0012', 'label': 'first'}, {'identifier': '12', 'label': 'second'},
                       {'identifier': '0013', 'label': 'third'}],
              'csv': {'columns': ['identifier', 'label'], 'delimiter': '|', 'encoding': 'utf-8'}},
        'B': {'threshold': 7, 'rows': [{'record_id': 'a', 'value': 8}, {'record_id': 'b', 'value': 7},
                                     {'record_id': 'c', 'value': 6}],
              'csv': {'columns': ['record_id', 'value'], 'delimiter': ';', 'encoding': 'utf-8'}},
        'S': {'entries': [{'account': 'a', 'kind': 'debit', 'magnitude': 9},
                          {'account': 'a', 'kind': 'credit', 'magnitude': 2},
                          {'account': 'b', 'kind': 'credit', 'magnitude': 3}],
              'csv': {'columns': ['account', 'net'], 'delimiter': '|', 'encoding': 'utf-8'}},
        'T': {'primary': [{'key': 'k1', 'revision': 2, 'value': 'p'}, {'key': 'k2', 'revision': 3, 'value': 'p'}],
              'secondary': [{'key': 'k1', 'revision': 2, 'value': 's'}, {'key': 'k2', 'revision': 1, 'value': 's'},
                            {'key': 'k3', 'revision': 4, 'value': 's'}]},
        'C': {'records': [{'record_id': 'a', 'status': 'rejected', 'issue': 'é|a'},
                          {'record_id': 'b', 'status': 'accepted', 'issue': 'omit'},
                          {'record_id': 'c', 'status': 'rejected', 'issue': '"quoted"\nline'}],
              'csv': {'columns': ['record_id', 'issue'], 'delimiter': '|'}},
        'R': {'records': [{'record_id': 'a', 'signed': True, 'sealed': False},
                          {'record_id': 'b', 'signed': False, 'sealed': True},
                          {'record_id': 'c', 'signed': True, 'sealed': True},
                          {'record_id': 'd', 'signed': False, 'sealed': False}]},
    }
    result = {}
    for family in a:
        result[family] = {'world_id': 'UNIT-' + family, 'template_id': 'UNIT-' + family,
                          'workspace': 'unit-workspace', 'language': 'EN', 'family': family,
                          'receiver_scope': 'unit-scope', 'parameter_seeds': {'A': 1, 'B': 2},
                          'receiver_convention': 'unset',
                          'A': {'task': {'data': a[family]}, 'oracle': {}},
                          'B': {'task': {'data': {**b[family], 'unit_marker': 'SEALED_B_UNIT_ONLY'}}, 'oracle': {}}}
    return result


class ExperienceFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != 'linux':
            raise RuntimeError('Linux oracle qualification only; Windows is AST/data authoring')
        helper = Path(os.environ.get('XP_FIXTURE_HELPER', str(ROOT / 'fixture_contract.py')))
        spec = importlib.util.spec_from_file_location('_independent_xp_fixture', helper)
        cls.c = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.c)
        cls.cases = unit_cases()

    def test_six_a_witnesses_have_literal_discriminating_results(self):
        c = self.c
        expected = {
            'I': [encoded({'identifiers': ['0012', '12']}), encoded({'identifiers': ['12', '12']})],
            'B': [b'{"eligible":[true]}\n', b'{"eligible":[false]}\n'],
            'S': [b'{"amounts":[-9]}\n', b'{"amounts":[9]}\n'],
            'T': [encoded({'retained': {'key': 'k', 'revision': 2, 'value': 'p'}}),
                  encoded({'retained': {'key': 'k', 'revision': 2, 'value': 's'}})],
            'C': [b'\xef\xbb\xbfprobe\r\nunit\r\n', b'probe\r\nunit\r\n'],
            'R': [b'{"approved":true}\n', b'{"approved":false}\n'],
        }
        for family, case in self.cases.items():
            conventions = list(c.CONVENTIONS[family])
            for selected in conventions:
                case = copy.deepcopy(case); case['receiver_convention'] = selected
                for index, attempted in enumerate(conventions):
                    with self.subTest(family=family, selected=selected, attempted=attempted):
                        target, raw, _ = c.expected_business(family, 'A', case['A']['task']['data'], attempted)
                        self.assertEqual(raw, expected[family][index])
                        feedback = c.feedback_from_a(case, {target: raw}, 'unit-check')
                        self.assertEqual(feedback['success'], selected == attempted)
                        self.assertEqual(feedback['observed']['attempted_convention'], attempted)
                        self.assertTrue(feedback['observed']['discriminating'])
                        self.assertEqual(set(feedback), {'schema', 'check_id', 'receiver_scope', 'success', 'violation_code', 'observed'})
                        self.assertNotIn('expected', feedback)

    def test_unavailable_or_unrecognized_actual_a_never_yields_inference(self):
        for family, case in self.cases.items():
            case = copy.deepcopy(case); case['receiver_convention'] = next(iter(self.c.CONVENTIONS[family]))
            unavailable = self.c.feedback_from_a(case, {}, 'unit-check')
            self.assertIsNone(unavailable['success'])
            self.assertFalse(unavailable['observed']['discriminating'])
            bad = self.c.feedback_from_a(case, {self.c.TARGETS[family]['A']: b'not a legal artifact'}, 'unit-check')
            self.assertFalse(bad['success'])
            self.assertFalse(bad['observed']['discriminating'])
            self.assertIsNone(bad['observed']['attempted_convention'])

    def test_distinct_b_goals_have_manual_semantic_vectors(self):
        c = self.c
        csv_rows = {
            'I.opaque': [['0012', 'first'], ['12', 'second'], ['0013', 'third']],
            'I.numeric': [['12', 'first'], ['13', 'third']],
            'B.inclusive': [['a', '8'], ['b', '7']], 'B.exclusive': [['a', '8']],
            'S.debit_negative': [['a', '-7'], ['b', '3']], 'S.debit_positive': [['a', '7'], ['b', '-3']],
            'C.bom': [['a', 'é|a'], ['c', '"quoted"\nline']],
            'C.plain': [['a', 'é|a'], ['c', '"quoted"\nline']],
        }
        for family, case in self.cases.items():
            for convention in c.CONVENTIONS[family]:
                with self.subTest(family=family, convention=convention):
                    target, raw, fmt = c.expected_business(family, 'B', case['B']['task']['data'], convention)
                    self.assertNotEqual(target, c.TARGETS[family]['A'])
                    if convention in csv_rows:
                        self.assertEqual(fmt['rows'], csv_rows[convention])
                        self.assertTrue(c._format_ok(raw, fmt))
                        if family == 'C':
                            self.assertEqual(raw.startswith(b'\xef\xbb\xbf'), convention == 'C.bom')
                    elif family == 'T':
                        side = 'primary' if convention == 'T.primary' else 'secondary'
                        self.assertEqual(fmt['value'], {'decisions': [
                            {'key': 'k1', 'winner_source': side, 'equal_revision': True},
                            {'key': 'k2', 'winner_source': 'primary', 'equal_revision': False},
                            {'key': 'k3', 'winner_source': 'secondary', 'equal_revision': False}], 'tie_count': 1})
                    else:
                        self.assertEqual(fmt['value'], {'archive': ['a', 'c'], 'held': ['b', 'd']} if convention == 'R.signed'
                                         else {'archive': ['b', 'c'], 'held': ['a', 'd']})

    def test_projection_has_real_common_authority_without_host_b_leakage(self):
        for family, case in self.cases.items():
            case = copy.deepcopy(case); case['receiver_convention'] = next(iter(self.c.CONVENTIONS[family]))
            for phase in ('A', 'B'):
                projection = self.c.project_case(case, phase)
                self.assertEqual(set(projection), {'world_id', 'template_id', 'workspace', 'language', 'family', 'task', 'observations', 'events'})
                self.assertEqual(len(projection['observations']), 1)
                self.assertEqual(len(projection['events']), 1)
                obs = projection['observations'][0]
                target = self.c.TARGETS[family][phase]
                self.assertEqual(projection['task']['target_dependencies'][target], obs['source_id'])
                self.assertEqual(projection['task']['conditions'], obs['metadata']['preconditions'])
                self.assertNotIn('receiver_convention', projection)
                self.assertNotIn('oracle', projection)
                self.assertNotIn('parameter_seeds', projection)
                if phase == 'A':
                    self.assertNotIn('SEALED_B_UNIT_ONLY', json.dumps(projection))

    def test_wrong_wellformed_lesson_is_graded_without_mutation(self):
        case = copy.deepcopy(self.cases['B']); case['receiver_convention'] = 'B.inclusive'
        feedback = self.c.feedback_from_a(case, {'eligibility.json': b'{"eligible":[false]}\n'}, 'unit-check')
        feedback_hash = digest(self.c.canonical(feedback).encode('utf-8'))
        candidate = {'schema': 'experience-procedure-v1', 'convention_id': 'B.exclusive',
                     'scope': case['receiver_scope'], 'evidence_refs': ['a' * 64, feedback_hash],
                     'text': 'Synthetic unit wrong lesson, not a model observation.'}
        before = copy.deepcopy(candidate)
        grade = self.c.grade_lesson(case, candidate, 'a' * 64, feedback_hash, feedback)
        self.assertTrue(grade['shape_valid']); self.assertTrue(grade['references_valid'])
        self.assertFalse(grade['choice_correct']); self.assertFalse(grade['valid'])
        self.assertEqual(candidate, before)
        bad = copy.deepcopy(candidate); bad['convention_id'] = []
        self.assertFalse(self.c.grade_lesson(case, bad, 'a' * 64, feedback_hash, feedback)['shape_valid'])
        self.assertFalse(self.c.grade_lesson(case, candidate, 'a' * 64, 'b' * 64, feedback)['evidence_available'])

    def test_oracle_checks_actual_bytes_types_control_and_protected_files(self):
        raw = b'{"approved":true}\n'
        expected = {'release.json': {**self.c.blob(raw), 'format': {'kind': 'json', 'value': {'approved': True}}}}
        oracle = {'expected_files': expected, 'unchanged_files': {'protected.json': digest(b'protected')},
                  'control': {'target': 'control.json', 'kind': 'cell-control-v1'}}
        observed = {'release.json': raw, 'protected.json': b'protected',
                    'control.json': encoded({'cell_id': 'unit-cell', 'completed': True})}
        self.assertTrue(self.c.verify_oracle(oracle, observed, cell_id='unit-cell')['passed'])
        for target, replacement in [('release.json', b'{"approved":1}\n'), ('protected.json', b'PROTECTED'),
                                    ('control.json', encoded({'cell_id': 'wrong-cell', 'completed': True}))]:
            bad = dict(observed); bad[target] = replacement
            self.assertFalse(self.c.verify_oracle(oracle, bad, cell_id='unit-cell')['passed'])
        bad = dict(observed); bad['outside.json'] = b'bad'
        self.assertFalse(self.c.verify_oracle(oracle, bad, cell_id='unit-cell')['passed'])

    def test_sealed_layout_and_frozen_file_hashes(self):
        fixture_path = Path(os.environ.get('XP_FIXTURE', str(ROOT / 'SEALED-FIXTURE.json')))
        plan_path = Path(os.environ.get('XP_PLAN', str(ROOT / 'PLAN.json')))
        manifest_path = Path(os.environ.get('XP_MANIFEST', str(ROOT / 'MANIFEST.json')))
        fixture_raw, plan_raw = fixture_path.read_bytes(), plan_path.read_bytes()
        fixture, plan = json.loads(fixture_raw), json.loads(plan_raw)
        manifest = json.loads(manifest_path.read_bytes())
        self.assertEqual(plan['dataset_sha256'], digest(fixture_raw))
        self.assertEqual(len(fixture['worlds']), 12)
        self.assertEqual(len(plan['episodes']), 48)
        self.assertEqual(len(plan['cells']), 288)
        self.assertEqual(len({c['cell_id'] for c in plan['cells']}), 288)
        cells = {c['cell_id']: c for c in plan['cells']}
        for cell in cells.values():
            self.assertEqual(set(cell), {'cell_id', 'world_id', 'template_id', 'model', 'arm', 'repetition'})
            self.assertIn(cell['repetition'], (1, 2))
        for episode in plan['episodes']:
            ids = [episode['a_cell_id'], episode['extract_cell_id'], *episode['b_cell_ids'].values()]
            self.assertEqual(len(set(ids)), 6)
            self.assertEqual(set(episode['b_cell_ids']), {'derived', 'raw', 'none', 'withdrawn'})
            self.assertTrue(all(cells[i]['world_id'] == episode['world_id'] for i in ids))
        for item in manifest['files']:
            path = manifest_path.parent / item['path']
            self.assertNotIn('..', Path(item['path']).parts)
            self.assertEqual(path.stat().st_size, item['bytes'])
            self.assertEqual(digest(path.read_bytes()), item['sha256'])

    def test_sealed_world_oracles_are_typed_discriminating_and_phase_specific(self):
        fixture = json.loads(Path(os.environ.get('XP_FIXTURE', str(ROOT / 'SEALED-FIXTURE.json'))).read_bytes())
        modes, seeds = {}, set()
        for case in fixture['worlds']:
            family = case['family']; modes.setdefault(family, set()).add(case['receiver_convention'])
            self.assertNotEqual(case['parameter_seeds']['A'], case['parameter_seeds']['B'])
            for value in case['parameter_seeds'].values():
                self.assertNotIn(value, seeds); seeds.add(value)
            variants = [self.c.expected_business(family, 'A', case['A']['task']['data'], rule)[1]
                        for rule in self.c.CONVENTIONS[family]]
            self.assertNotEqual(*variants)
            for phase in ('A', 'B'):
                task, oracle = case[phase]['task'], self.c.get_oracle(case, phase)
                self.assertEqual(set(task), {'brief', 'query', 'as_of', 'conditions', 'data', 'seed_files', 'allowed_targets', 'target_dependencies'})
                target, raw, fmt = self.c.expected_business(family, phase, task['data'], case['receiver_convention'])
                spec = oracle['expected_files'][target]
                self.assertEqual(base64.b64decode(spec['base64']), raw)
                self.assertEqual(spec['format'], fmt)
                self.assertTrue(self.c._format_ok(raw, fmt))
                self.assertNotIn('protected.json', task['allowed_targets'])
                self.assertEqual(len(task['allowed_targets']), 2)
        for family, choices in modes.items():
            self.assertEqual(choices, set(self.c.CONVENTIONS[family]))


if __name__ == '__main__':
    unittest.main()
