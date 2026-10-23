"""Linux-only, synthetic, mock-only qualification of the unchanged paid binding.

Run separately AFTER fake-provider absence/process tests. Every credential, grant,
budget and response here is synthetic and temporary. MockTransport plus raw-socket
denial prevents HTTP/DNS fallback. This is neither a paid grant nor model evidence.
Root additionally runs this suite with PrivateNetwork=yes; no real key is opened.
"""
import asyncio
from contextlib import ExitStack
import copy
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


class PaidBindingMockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != 'linux':
            raise RuntimeError('Paid-binding mock qualification requires the isolated Linux native unit.')
        source = os.environ.get('ACTION_SOURCE') or os.environ.get('ACTION_SUPPORT_SOURCE')
        if source is None:
            raise RuntimeError('ACTION_SOURCE must identify the frozen support source explicitly.')
        cls.source_path = Path(source).resolve()
        spec = importlib.util.spec_from_file_location('synthetic_paid_binding_support', cls.source_path)
        cls.support = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.support)
        cls.provider_path = Path(os.environ['ACTION_PROVIDER_SOURCE']).resolve()
        cls.reader_path = Path(os.environ['ACTION_CREDENTIAL_READER']).resolve()
        # Import only in this separate paid-binding test invocation, never in the
        # fake-provider suite or the support module's fake execution path.
        try:
            import httpx
        except ImportError:
            dependency = os.environ.get('ACTION_HTTPX_SITE_PACKAGES')
            if dependency is None:
                raise RuntimeError('Explicit ACTION_HTTPX_SITE_PACKAGES is required when httpx is absent.')
            dependency = Path(dependency).resolve()
            if not dependency.is_dir():
                raise RuntimeError('ACTION_HTTPX_SITE_PACKAGES must be an existing read-only dependency location.')
            sys.path.insert(0, str(dependency))
            import httpx
        cls.httpx = httpx
        cls.provider = cls.support._bound_module(cls.provider_path, cls.support.PROVIDER_SHA256, 'provider')

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='SYNTHETIC-MOCK-ONLY-paid-binding-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.scope = {'synthetic': True, 'mock_only': True, 'real_credentials': False,
                      'real_provider_requests': 0, 'authorized_model_experiment': False}
        (self.directory / 'SYNTHETIC-MOCK-ONLY.scope.json').write_text(json.dumps(self.scope), encoding='utf-8')
        self.key_path = self.directory / 'SYNTHETIC-MOCK-ONLY.key'
        self.synthetic_key = 'SYNTHETIC-MOCK-ONLY-NOT-A-VALID-PROVIDER-CREDENTIAL'
        self.key_path.write_text(self.synthetic_key + '\n', encoding='utf-8')
        self.key_path.chmod(0o600)
        self.assertEqual(stat.S_IMODE(self.key_path.stat().st_mode), 0o600)
        self.credential_reads = []
        self.posts = []

    @staticmethod
    def _bytes(value):
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')

    def _write(self, path, value):
        raw = self._bytes(value)
        path.write_bytes(raw)
        path.chmod(0o600)
        return hashlib.sha256(raw).hexdigest()

    def _synthetic_case(self, model='gpt-6-luna', label='ONE', arm='memory_off'):
        support = self.support
        profile_name, effort = support.MODELS[model]
        rates = (Decimal('0.0000001'), Decimal('0.0000005')) if model == 'gpt-6-luna' else (Decimal('0.000002'), Decimal('0.00001'))
        unit = Decimal(11264) * rates[0] + Decimal(2048) * rates[1]
        cell = {'cell_id': 'SYNTHETIC-MOCK-' + label, 'world_id': 'SYNTHETIC-WORLD',
                'template_id': 'SYNTHETIC-TEMPLATE', 'model': model, 'arm': arm, 'repetition': 1}
        dataset = hashlib.sha256(self._bytes({'schema': 'synthetic-mock-only-dataset-v1', **self.scope})).hexdigest()
        plan = hashlib.sha256(self._bytes({'synthetic_mock_only': True, 'cell': cell})).hexdigest()
        projection = {'schema': 'persistent-memory.action-transfer.phase.v1', 'phase': 'propose',
                      'dataset_sha256': dataset, 'plan_sha256': plan, 'cell': cell,
                      'workspace': 'synthetic-mock-workspace', 'language': 'EN', 'family': 'selfcontained',
                      'payload': {'task': {'brief': 'Synthetic transport qualification only; no business oracle.',
                          'query': 'synthetic', 'as_of': None, 'conditions': {}, 'data': {'mock_only': True},
                          'seed_files': {}, 'allowed_targets': ['control.json', 'decision.json'],
                          'target_dependencies': {'control.json': None, 'decision.json': None}}}}
        expiry = time.time() + 120
        profile = {'schema_version': 1, 'profile': profile_name, 'purpose': 'generation',
                   'dataset_sha256': dataset, 'cells': [{'cell_id': cell['cell_id'], 'task_id': cell['world_id'],
                       'stage': 'rep1', 'arm': cell['arm']}], 'max_requests': 1, 'wall_seconds': 300,
                   'per_request_usd': str(unit), 'max_total_usd': str(unit)}
        budget = {**copy.deepcopy(profile), 'authorized_for_execution': True, 'price_verified': True,
                  'tokenizer_bound_verified': True, 'reasoning_total_bound_verified': True,
                  'model': model, 'endpoint': 'https://api.openai.com/v1/chat/completions',
                  'request_options': {'reasoning_effort': effort}, 'response_models': [model],
                  'input_tokens_per_request': 11264, 'output_tokens_per_request': 2048,
                  'full_request_bytes': 10240, 'message_bytes': 10240, 'framing_token_allowance': 1024,
                  'timeout_seconds': 90, 'expires_at_epoch': expiry}
        budget_path = self.directory / ('SYNTHETIC-MOCK-ONLY-' + label + '-budget.json')
        budget_pin = self._write(budget_path, budget)
        grant = {'schema': 'persistent-memory.action-transfer.grant.v1', 'authorized_for_execution': True,
                 'provider_sha256': support.PROVIDER_SHA256, 'support_sha256': hashlib.sha256(self.source_path.read_bytes()).hexdigest(),
                 'dataset_sha256': dataset, 'cell_id': cell['cell_id'], 'model': model,
                 'expires_at_epoch': expiry, 'budget': {'path': budget_path.name, 'sha256': budget_pin},
                 'profile': copy.deepcopy(profile),
                 'credential': {'path': str(self.key_path), 'env_file': False, 'field': 'OPENAI_API_KEY'}}
        grant_path = self.directory / ('SYNTHETIC-MOCK-ONLY-' + label + '-grant.json')
        grant_pin = self._write(grant_path, grant)
        return {'projection': projection, 'profile': profile, 'budget': budget, 'grant': grant,
                'budget_path': budget_path, 'grant_path': grant_path, 'grant_pin': grant_pin,
                'ledger': self.directory / ('SYNTHETIC-MOCK-ONLY-' + label + '-ledger.sqlite'), 'unit': unit}

    def _client(self, case, *, forbid_credential=False, pin=None, factory=None):
        support = self.support
        original_loader = support._bound_module
        with ExitStack() as stack:
            def loader(path, expected, label):
                if label == 'credential_reader' and forbid_credential:
                    raise AssertionError('Rejected grant/budget reached the credential-reader import.')
                module = original_loader(path, expected, label)
                if label == 'credential_reader':
                    real_read = module.read_credential
                    def read_only_synthetic(path, **options):
                        self.assertEqual(Path(path).resolve(), self.key_path.resolve())
                        self.assertTrue(case['ledger'].is_file(), 'Budget must open the real durable ledger before credential reading.')
                        self.assertEqual(stat.S_IMODE(case['ledger'].stat().st_mode), 0o600)
                        with sqlite3.connect(case['ledger']) as connection:
                            self.assertEqual(connection.execute('SELECT COUNT(*) FROM reservations').fetchone()[0], 0)
                        self.credential_reads.append(str(path))
                        return real_read(path, **options)
                    stack.enter_context(patch.object(module, 'read_credential', side_effect=read_only_synthetic))
                return module
            stack.enter_context(patch.object(support, '_bound_module', side_effect=loader))
            return (factory or support._paid_client)(case['projection'], case['grant_path'], pin or case['grant_pin'],
                self.provider_path, self.reader_path, case['ledger'])

    def _mock(self, client, case, expected_prompt=None, response_body='{"synthetic_mock_only":true}'):
        support = self.support
        def post(request):
            self.assertEqual(request.method, 'POST')
            self.assertEqual(str(request.url), 'https://api.openai.com/v1/chat/completions')
            self.assertEqual(request.headers['authorization'], 'Bearer ' + self.synthetic_key)
            actual = json.loads(request.content)
            fingerprint = hashlib.sha256(support.canonical(actual).encode('utf-8')).hexdigest()
            with sqlite3.connect(case['ledger']) as connection:
                rows = connection.execute('SELECT cell_id,budget_sha,request_sha,amount FROM reservations').fetchall()
                self.assertEqual(connection.execute('PRAGMA synchronous').fetchone()[0], 2)
            self.assertEqual(rows, [(case['projection']['cell']['cell_id'], case['grant']['budget']['sha256'], fingerprint, str(case['unit']))])
            self.assertEqual(client.trace['request_sha256'], fingerprint)
            self.assertEqual(client.trace['status'], 'reserved')
            self.assertIs(client.trace['provider_called'], True)
            prompt = expected_prompt if expected_prompt is not None else actual['messages'][0]['content']
            self.assertIsInstance(prompt, str)
            self.assertEqual(actual['messages'], [{'role': 'user', 'content': prompt}])
            self.assertEqual(actual['max_completion_tokens'], 2048)
            self.assertEqual(actual['reasoning_effort'], support.MODELS[case['projection']['cell']['model']][1])
            self.assertNotIn('temperature', actual)
            preflight = support._request_preflight(actual['model'], prompt)
            self.assertEqual(client.trace['request_sha256'], preflight['request_sha256'])
            self.assertEqual(client.trace['input_token_upper_bound'], preflight['input_token_upper_bound'])
            self.posts.append(fingerprint)
            return self.httpx.Response(200, json={'model': actual['model'],
                'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': response_body}}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 8, 'total_tokens': 18}})
        client._transport = self.httpx.MockTransport(post)

    def _send(self, client, prompt):
        # No fallback to DNS, TCP, UNIX sockets or a real HTTP transport is allowed.
        with (patch('socket.socket.connect', side_effect=AssertionError('Raw network is forbidden in synthetic mock tests.')),
              patch('socket.create_connection', side_effect=AssertionError('Network fallback is forbidden.')),
              patch('socket.getaddrinfo', side_effect=AssertionError('DNS is forbidden.'))):
            return asyncio.run(client.agenerate(prompt=prompt, max_tokens=2048, temperature=None))

    def test_missing_grant_does_not_import_provider_or_read_credential(self):
        case = self._synthetic_case(label='CLOSED-NO-GRANT')
        with patch.object(self.support, '_bound_module', side_effect=AssertionError('Missing grant imported provider.')):
            with self.assertRaises(self.support.ActionTransferError):
                self.support._paid_client(case['projection'], None, None, self.provider_path, self.reader_path, case['ledger'])
        self.assertFalse(case['ledger'].exists())
        self.assertEqual(self.credential_reads, [])
        self.assertEqual(self.posts, [])

    def test_valid_binding_both_models_reserves_before_mock_post_and_never_retries(self):
        for model, expected_unit in (('gpt-6-luna', Decimal('0.0021504')), ('gpt-6.1-sol', Decimal('0.043008'))):
            with self.subTest(model=model):
                case = self._synthetic_case(model, 'VALID-' + model)
                reads_before, posts_before = len(self.credential_reads), len(self.posts)
                client = self._client(case)
                self.assertEqual(len(self.credential_reads), reads_before + 1)
                self.assertEqual(client.budget.unit, expected_unit)
                self.assertEqual(client.budget.max_requests, 1)
                self.assertIsNone(client.trace)
                prompt = 'Synthetic mock-only one-request qualification.'
                self._mock(client, case, prompt)
                self.assertEqual(self._send(client, prompt), '{"synthetic_mock_only":true}')
                self.assertEqual(len(self.posts), posts_before + 1)
                self.assertEqual(client.trace['status'], 'completed')
                self.assertEqual(client.trace['usage']['total_tokens'], 18)
                with self.assertRaises(self.provider.BudgetError):
                    self._send(client, prompt)
                self.assertEqual(len(self.posts), posts_before + 1)
                # A reconstructed binding cannot reopen the same ledger or read a key again.
                with self.assertRaises(self.provider.BudgetError):
                    self._client(case, forbid_credential=True)
                self.assertEqual(len(self.credential_reads), reads_before + 1)

    def test_invalid_grants_and_tampered_budgets_never_reach_credential_reader(self):
        mutations = ('unapproved', 'expired', 'wrong_cell', 'wrong_model', 'wrong_support', 'wrong_profile_cell',
                     'wrong_pin', 'tampered_budget', 'unapproved_budget', 'expired_budget', 'changed_limits', 'changed_rates')
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                case = self._synthetic_case(label='REJECT-' + mutation)
                grant, budget = case['grant'], case['budget']
                if mutation == 'unapproved': grant['authorized_for_execution'] = False
                elif mutation == 'expired': grant['expires_at_epoch'] = time.time() - 1
                elif mutation == 'wrong_cell': grant['cell_id'] = 'SYNTHETIC-WRONG-CELL'
                elif mutation == 'wrong_model': grant['model'] = 'gpt-6.1-sol'
                elif mutation == 'wrong_support': grant['support_sha256'] = '0' * 64
                elif mutation == 'wrong_profile_cell': grant['profile']['cells'][0]['cell_id'] = 'SYNTHETIC-WRONG-CELL'
                elif mutation == 'tampered_budget':
                    budget['wall_seconds'] = 301
                    self._write(case['budget_path'], budget)  # Keep the old, now incorrect grant pin for these bytes.
                elif mutation in ('unapproved_budget', 'expired_budget', 'changed_limits', 'changed_rates'):
                    if mutation == 'unapproved_budget': budget['authorized_for_execution'] = False
                    elif mutation == 'expired_budget': budget['expires_at_epoch'] = time.time() - 1
                    elif mutation == 'changed_limits': budget['full_request_bytes'] = 10241
                    else:
                        budget['per_request_usd'] = budget['max_total_usd'] = '0.001'
                        grant['profile']['per_request_usd'] = grant['profile']['max_total_usd'] = '0.001'
                    grant['budget']['sha256'] = self._write(case['budget_path'], budget)
                case['grant_pin'] = self._write(case['grant_path'], grant)
                with self.assertRaises((self.support.ActionTransferError, self.provider.BudgetError)):
                    self._client(case, forbid_credential=True, pin='0' * 64 if mutation == 'wrong_pin' else None)
                self.assertEqual(self.credential_reads, [])
                self.assertEqual(self.posts, [])
                self.assertFalse(case['ledger'].exists())

    def test_complete_request_boundary_matches_real_client_before_reservation(self):
        for model in self.support.MODELS:
            with self.subTest(model=model):
                case = self._synthetic_case(model, 'BOUNDARY-' + model)
                client = self._client(case)
                overhead = self.support._request_preflight(model, '')['full_request_bytes']
                exact = 'x' * (10240 - overhead)
                preflight = self.support._request_preflight(model, exact)
                self.assertEqual(preflight['full_request_bytes'], 10240)
                self.assertEqual(preflight['input_token_upper_bound'], 11264)
                with self.assertRaises(self.support.ActionTransferError):
                    self.support._request_preflight(model, exact + 'x')
                self._mock(client, case, exact)
                posts_before = len(self.posts)
                with self.assertRaises(self.provider.BudgetError):
                    self._send(client, exact + 'x')
                self.assertEqual(len(self.posts), posts_before)
                self.assertIsNone(client.trace)
                with sqlite3.connect(case['ledger']) as connection:
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM reservations').fetchone()[0], 0)
                self._send(client, exact)
                self.assertEqual(len(self.posts), posts_before + 1)


    def test_experience_extraction_uses_real_cell_budget_and_explicit_ledger_once(self):
        support = self.support
        case = self._synthetic_case(label='XP-EXTRACT', arm='none')
        projection = case['projection']
        projection.update(schema='persistent-memory.experience.phase.v1', phase='extract', family='I',
            payload={'conventions': {'I.opaque': 'Keep digits verbatim.', 'I.numeric': 'Normalize numeric IDs.'}})
        a_cell = {**projection['cell'], 'cell_id': 'SYNTHETIC-MOCK-XP-A'}
        # These are synthetic receipt records, not evidence of real process exits.
        # Real subprocess boundaries are qualified by the separate fake CLI suite.
        a = {'cell': a_cell, 'dataset_sha256': projection['dataset_sha256'],
             'plan_sha256': projection['plan_sha256'], 'pid': os.getpid() + 1000000, 'ended_ns': 2,
             'prompt': 'Synthetic A witness: keep 01 and 1.', 'proposal_raw': '{"ids":["01","1"]}',
             'status': 'completed', 'category': 'pending_independent_verification',
             'writes': [], 'blocked': [], 'after': {}}
        a['prompt_sha256'] = support.digest(a['prompt'].encode())
        artifact_pin = support.digest(b'{"ids":["01","1"]}\n')
        verification = {'cell': a_cell, 'dataset_sha256': projection['dataset_sha256'],
             'plan_sha256': projection['plan_sha256'], 'effect_verified': True, 'task_success': True,
             'category': 'exact_task', 'checks': {},
             'observed_inventory': {'import.json': {'kind': 'file', 'sha256': artifact_pin, 'bytes': 19}},
             'pid': a['pid'] + 1, 'started_ns': 4, 'ended_ns': 5,
             'p2_exit': {'pid': a['pid'], 'returncode': 0, 'exited_ns': 3}}
        a_exit = {'pid': verification['pid'], 'returncode': 0, 'exited_ns': 6}
        feedback = {'schema': 'experience-feedback-v1', 'check_id': 'synthetic-mock-feedback',
             'receiver_scope': 'synthetic-mock-receiver', 'success': True, 'violation_code': None,
             'observed': {'artifact_sha256': artifact_pin, 'attempted_convention': 'I.opaque', 'discriminating': True}}
        source = support.experience_input(a, verification, feedback)
        # A wrong, well-formed lesson still goes through the real paid binding.
        lesson = {'schema': 'experience-procedure-v1', 'convention_id': 'I.numeric',
             'scope': feedback['receiver_scope'], 'evidence_refs': [
                 support.digest(support.canonical(source['trace']).encode()),
                 support.digest(support.canonical(source['feedback']).encode())], 'text': 'Normalize numeric IDs.'}
        real_paid_client = support._paid_client
        clients = []

        def bound_client(value, grant_path, grant_pin, provider_path, reader_path, ledger_path):
            self.assertEqual(value, projection)
            self.assertEqual((grant_path, grant_pin, provider_path, reader_path, ledger_path),
                (case['grant_path'], case['grant_pin'], self.provider_path, self.reader_path, case['ledger']))
            client = self._client(case, factory=real_paid_client)
            self._mock(client, case, response_body=support.canonical(lesson))
            clients.append(client)
            return client

        with (patch.object(support, '_paid_client', side_effect=bound_client) as binding,
              patch('socket.socket.connect', side_effect=AssertionError('Raw network is forbidden.')),
              patch('socket.create_connection', side_effect=AssertionError('Network fallback is forbidden.')),
              patch('socket.getaddrinfo', side_effect=AssertionError('DNS is forbidden.'))):
            receipt = support.extract_procedure(projection, a, verification, a_exit, feedback, mode='paid',
                grant_path=case['grant_path'], grant_sha256=case['grant_pin'], provider_path=self.provider_path,
                credential_reader_path=self.reader_path, ledger_path=case['ledger'])
        binding.assert_called_once()
        self.assertEqual(receipt['status'], 'completed')
        self.assertEqual(receipt['procedure'], lesson)
        self.assertFalse(receipt['candidate_promoted'])
        self.assertEqual(receipt['input'], source)
        self.assertIn(support.canonical(source), receipt['prompt'])
        self.assertEqual(receipt['preflight']['request_sha256'], clients[0].trace['request_sha256'])
        self.assertEqual(receipt['usage']['total_tokens'], 18)
        self.assertTrue(receipt['provider_called'])
        self.assertEqual(len(self.credential_reads), 1)
        self.assertEqual(len(self.posts), 1)
        with self.assertRaises(self.provider.BudgetError):
            self._send(clients[0], receipt['prompt'])
        with self.assertRaises(self.provider.BudgetError):
            self._client(case, forbid_credential=True)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(len(self.credential_reads), 1)
