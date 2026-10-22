"""Single-attempt provider boundary with durable worst-cost reservation."""
from __future__ import annotations

import asyncio
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import time

import httpx


class BudgetError(ValueError):
    pass


class IncompleteProviderResponse(BudgetError):
    """A paid attempt was observed but supplied no complete semantic answer."""


def require(ok, reason):
    if not ok:
        raise BudgetError(reason)


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


TASK_UTILITY_DATASET_SHA = '2cbb6559c4551a48b88d21ec84b724fc6d5008360a5ab738ee24e8a63a7bcbd2'
TASK_UTILITY_CELLS = tuple(
    {'cell_id': task + ':' + stage + ':' + arm, 'task_id': task, 'stage': stage, 'arm': arm}
    for task in ('TU01', 'TU02', 'TU03', 'TU04')
    for stage, arm in (('selector', 'task_selected'), ('action', 'no_memory'),
                       ('action', 'current_reference'), ('action', 'task_selected'))
)


VERIFIER_TWOCASE_DATASET_SHA = '394c9ef33bf8940f8c29c4aef8bb4e22ef881433009b70295635f1ba1e694019'
VERIFIER_TWOCASE_CELLS = ({'cell_id': 'C12:B0:regression-20261009', 'task_id': 'C12', 'stage': 'verification', 'arm': 'B0'}, {'cell_id': 'C03:B0:regression-20261009', 'task_id': 'C03', 'stage': 'verification', 'arm': 'B0'})


NATIVE_CONTENT_DATASET_SHA = '83d1f98ae068e00528041d85c688759a00408214aef63b4998213b73779ed165'
NATIVE_CONTENT_CELLS = ({'cell_id': 'C01:reference:initial', 'task_id': 'C01', 'stage': 'initial', 'arm': 'reference'}, {'cell_id': 'C01:native:initial', 'task_id': 'C01', 'stage': 'initial', 'arm': 'native'}, {'cell_id': 'C03:native:initial', 'task_id': 'C03', 'stage': 'initial', 'arm': 'native'}, {'cell_id': 'C03:reference:initial', 'task_id': 'C03', 'stage': 'initial', 'arm': 'reference'}, {'cell_id': 'C05:reference:initial', 'task_id': 'C05', 'stage': 'initial', 'arm': 'reference'}, {'cell_id': 'C05:native:initial', 'task_id': 'C05', 'stage': 'initial', 'arm': 'native'}, {'cell_id': 'C12:native:initial', 'task_id': 'C12', 'stage': 'initial', 'arm': 'native'}, {'cell_id': 'C12:reference:initial', 'task_id': 'C12', 'stage': 'initial', 'arm': 'reference'})

# Prospective only: historical profiles retain their exact provider contract.
VOLUME_MODELS = {
    'volume_luna6_none_v1': ('gpt-6-luna', 'none', Decimal('0.0000001'), Decimal('0.0000005')),
    'volume_sol61_low_v1': ('gpt-6.1-sol', 'low', Decimal('0.000002'), Decimal('0.00001')),
}


class Budget:
    def __init__(self, path, expected_sha256, ledger_path, *, tokenizer, max_requests=36, dataset_sha256=None, prospective_profile=None):
        self.volume = bool(type(prospective_profile) is dict and prospective_profile.get('profile') in VOLUME_MODELS)
        if self.volume:
            self._init_volume(path, expected_sha256, ledger_path, tokenizer, max_requests,
                              dataset_sha256, prospective_profile)
            return
        prospective = prospective_profile is not None
        profile = None
        openai_native = False
        if prospective:
            require(type(prospective_profile) is dict and set(prospective_profile) == {'schema_version','profile','dataset_sha256','cells','max_requests','wall_seconds','per_request_usd','max_total_usd'}, 'prospective_profile_schema')
            profile = json.loads(json_bytes(prospective_profile))
            openai_native = profile.get('profile') in ('voice_openai41_native_pair_v1', 'native_rule_context_four_arms_v1', 'native_rule_context_four_arms_v2', 'native_memory_rule_readonly_pair_v1')
            expected = {'native_utility_three_pairs_v1': (6, 600, '0.12'), 'voice_preference_utility_pair_v1': (2, 300, '0.04'), 'voice_openai41_native_pair_v1': (2, 300, '0.08'), 'native_rule_context_four_arms_v1': (8, 600, '0.32'), 'native_rule_context_four_arms_v2': (8, 600, '0.32'), 'native_memory_rule_readonly_pair_v1': (2, 300, '0.08')}
            require(profile.get('schema_version') == 1 and profile.get('profile') in expected, 'prospective_profile_unknown')
            cap, seconds, amount = expected[profile['profile']]
            require(type(max_requests) is int and max_requests == profile.get('max_requests') == cap and profile.get('wall_seconds') == seconds and profile.get('per_request_usd') == ('0.04' if openai_native else '0.02') and profile.get('max_total_usd') == amount, 'prospective_profile_limits')
            require(type(dataset_sha256) is str and len(dataset_sha256) == 64 and all(c in '0123456789abcdef' for c in dataset_sha256) and profile.get('dataset_sha256') == dataset_sha256, 'prospective_dataset_binding')
            cells = profile.get('cells')
            require(type(cells) is list and len(cells) == cap and all(type(cell) is dict and set(cell) == {'cell_id','task_id','stage','arm'} and all(type(value) is str and 0 < len(value) <= 128 for value in cell.values()) for cell in cells), 'prospective_cells_schema')
            require(len({cell['cell_id'] for cell in cells}) == cap, 'prospective_cells_unique')
            if profile['profile'] in ('native_rule_context_four_arms_v1', 'native_rule_context_four_arms_v2'):
                expected_cells = [
                    {'cell_id': 'NRCP01:' + arm + ':turn' + str(turn),
                     'task_id': 'NRCP01', 'stage': 'transfer', 'arm': arm}
                    for arm in ('recovered_rule', 'absent', 'out_of_scope_placebo', 'oracle')
                    for turn in (1, 2)]
                require(cells == expected_cells, 'pilot_exact_cells_required')
            if profile['profile'] == 'native_memory_rule_readonly_pair_v1':
                task_id = cells[0]['task_id']
                require(cells == [
                    {'cell_id': task_id + ':native_rule_use:turn' + str(turn),
                     'task_id': task_id, 'stage': 'native_rule_use', 'arm': 'native_rule_use'}
                    for turn in (1, 2)], 'rule_readonly_exact_pair_required')
        native_v2 = prospective and profile['profile'] in ('native_rule_context_four_arms_v2', 'native_memory_rule_readonly_pair_v1')
        raw = Path(path).read_bytes()
        require(type(expected_sha256) is str and len(expected_sha256) == 64 and hashlib.sha256(raw).hexdigest() == expected_sha256, 'budget_not_frozen')
        b = json.loads(raw)
        require(b.get('schema_version') == 1 and b.get('authorized_for_execution') is True, 'budget_not_authorized')
        require(all(b.get(k) is True for k in ('price_verified','tokenizer_bound_verified','reasoning_total_bound_verified')), 'budget_proof_missing')
        require((b.get('model') == 'gpt-4.1' and b.get('endpoint') == 'https://api.openai.com/v1/chat/completions') if openai_native else (b.get('model') == 'deepseek-v4-pro' and b.get('endpoint') == 'https://api.deepseek.com/chat/completions'), 'provider_not_allowed')
        require(b.get('request_options') == ({} if openai_native else {'thinking':{'type':'disabled'}}), ('reasoning_options_changed' if openai_native else 'reasoning_not_disabled'))
        if openai_native:
            require(b.get('response_models') == ['gpt-4.1','gpt-4.1-2025-04-14'] and b.get('full_request_bytes') == (10240 if native_v2 else 9216) and b.get('framing_token_allowance') == 1024, 'openai_native_fixed_binding')
        require(type(max_requests) is int and (max_requests in (2,3,8,16,36) or prospective and max_requests == 6), 'request_cap_not_allowed')
        if prospective:
            require(all(b.get(key) == profile[key] for key in profile), 'prospective_budget_binding')
        if max_requests == 2 and not prospective:
            require(dataset_sha256 == VERIFIER_TWOCASE_DATASET_SHA and
                    b.get('dataset_sha256') == dataset_sha256 and
                    b.get('profile') == 'verifier_two_exposed_b0_v1', 'verifier_two_profile_binding')
            require(b.get('cells') == list(VERIFIER_TWOCASE_CELLS), 'verifier_two_cells_changed')
        if max_requests == 8 and not prospective:
            require(dataset_sha256 == NATIVE_CONTENT_DATASET_SHA and b.get('dataset_sha256') == dataset_sha256
                    and b.get('profile') == 'native_content_four_exposed_v1', 'native_content_profile_binding')
            require(b.get('cells') == list(NATIVE_CONTENT_CELLS), 'native_content_cells_changed')
        if max_requests == 3 and not prospective:
            require(type(dataset_sha256) is str and len(dataset_sha256) == 64 and all(c in '0123456789abcdef' for c in dataset_sha256) and dataset_sha256 != '271dcdd1d7025a15d41f9c4e766d8cfc1dad7625c2ce0db489e3be7cede9c037', 'new_input_pin_required')
            require(b.get('profile') == 'single_recall_three_arms_v1' and b.get('dataset_sha256') == dataset_sha256, 'prospective_budget_binding_required')
        if max_requests == 16 and not prospective:
            require(type(dataset_sha256) is str and dataset_sha256 == TASK_UTILITY_DATASET_SHA and
                    b.get('dataset_sha256') == dataset_sha256 and
                    b.get('profile') == 'task_utility_four_dev_v1', 'task_utility_profile_binding')
            require(b.get('cells') == list(TASK_UTILITY_CELLS), 'task_utility_cells_changed')
        require(b.get('max_requests') == max_requests and b.get('input_tokens_per_request') == (11264 if native_v2 else 10240 if openai_native else 9216) and b.get('output_tokens_per_request') == (2048 if openai_native else 768) and b.get('message_bytes') == (10240 if native_v2 else 9216 if prospective and profile['profile'] == 'native_rule_context_four_arms_v1' else 8192), 'budget_limits_changed')
        wall = b.get('wall_seconds')
        expires = b.get('expires_at_epoch') if prospective or max_requests in (2,3,8,16) else None
        if prospective:
            require(type(wall) is int and wall == profile['wall_seconds'], 'time_limits_changed')
            require(type(expires) in (int,float) and time.time() < expires < float('inf'), 'budget_expired_or_invalid')
        elif max_requests == 2 and not prospective:
            require(type(wall) is int and 0 < wall <= 300, 'time_limits_changed')
            require(type(expires) in (int,float) and time.time() < expires < float('inf'), 'budget_expired_or_invalid')
        elif max_requests == 8 and not prospective:
            require(type(wall) is int and 0 < wall <= 900, 'time_limits_changed')
            require(type(expires) in (int,float) and time.time() < expires < float('inf'), 'budget_expired_or_invalid')
        elif max_requests == 3 and not prospective:
            require(type(wall) is int and 0 < wall <= 600, 'time_limits_changed')
            require(type(expires) in (int,float) and time.time() < expires < float('inf'), 'budget_expired_or_invalid')
        elif max_requests == 16 and not prospective:
            require(type(wall) is int and 0 < wall <= 1200, 'time_limits_changed')
            require(type(expires) in (int,float) and time.time() < expires < float('inf'), 'budget_expired_or_invalid')
        else:
            require(wall == 3600, 'time_limits_changed')
        require(b.get('timeout_seconds') == 90, 'time_limits_changed')
        require(type(b.get('per_request_usd')) is str and type(b.get('max_total_usd')) is str, 'decimal_strings_required')
        unit, total = Decimal(b['per_request_usd']), Decimal(b['max_total_usd'])
        require(unit.is_finite() and total.is_finite() and unit > 0 and 0 < total <= 2 and unit * max_requests <= total, 'whole_envelope_not_funded')
        if prospective:
            require(unit == Decimal(profile['per_request_usd']) and total == Decimal(profile['max_total_usd']), 'prospective_funding_changed')
        elif max_requests == 2 and not prospective:
            require(unit == Decimal('0.02') and total == Decimal('0.04'), 'verifier_two_funding_changed')
        if max_requests == 8 and not prospective:
            require(unit == Decimal('0.02') and total == Decimal('0.16'), 'native_content_funding_changed')
        if max_requests == 3 and not prospective:
            require(unit == Decimal('0.02') and total == Decimal('0.06'), 'prospective_funding_changed')
        if max_requests == 16 and not prospective:
            require(unit == Decimal('0.02') and total == Decimal('0.32'), 'task_utility_funding_changed')
        # Worst-case peak prices from the fixed official ratecard; no cache discount.
        require(unit >= (Decimal('0.038912') if native_v2 else Decimal('0.036864') if openai_native else Decimal('0.0152064')), 'reservation_below_ratecard')
        self.openai_native = openai_native
        # Fixed from the validated profile, never from later mutable config.
        self._native_profile = profile['profile'] if openai_native else None
        self._native_limits = (10240, 11264, 10240) if native_v2 else (9216, 10240, 9216 if prospective and profile['profile'] == 'native_rule_context_four_arms_v1' else 8192)
        require(callable(tokenizer), 'real_tokenizer_required')
        self.config, self.sha256, self.unit, self.total, self.tokenizer = b, expected_sha256, unit, total, tokenizer
        self.max_requests, self.wall, self.expires = max_requests, wall, expires
        self.cell_ids = frozenset(item['cell_id'] for item in profile['cells']) if prospective else (frozenset(item['cell_id'] for item in NATIVE_CONTENT_CELLS) if max_requests == 8 else frozenset(item['cell_id'] for item in VERIFIER_TWOCASE_CELLS) if max_requests == 2 else frozenset(item['cell_id'] for item in TASK_UTILITY_CELLS) if max_requests == 16 else None)
        self._open_ledger(ledger_path)

    def _init_volume(self, path, expected_sha256, ledger_path, tokenizer, max_requests, dataset_sha256, profile):
        require(type(profile) is dict and set(profile) == {'schema_version','profile','purpose','dataset_sha256','cells','max_requests','wall_seconds','per_request_usd','max_total_usd'}, 'volume_profile_schema')
        profile = json.loads(json_bytes(profile))
        require(profile['schema_version'] == 1 and profile['purpose'] in ('generation','judge'), 'volume_purpose')
        require(type(max_requests) is int and 1 <= max_requests <= (3 if profile['purpose'] == 'generation' else 1)
                and profile['max_requests'] == max_requests and profile['wall_seconds'] == 300, 'volume_request_limits')
        require(type(dataset_sha256) is str and len(dataset_sha256) == 64
                and all(c in '0123456789abcdef' for c in dataset_sha256)
                and profile['dataset_sha256'] == dataset_sha256, 'volume_dataset_binding')
        cells = profile['cells']
        require(type(cells) is list and len(cells) == max_requests and all(
            type(c) is dict and set(c) == {'cell_id','task_id','stage','arm'}
            and all(type(v) is str and 0 < len(v) <= 128 for v in c.values()) for c in cells)
            and len({c['cell_id'] for c in cells}) == max_requests, 'volume_cells')
        raw = Path(path).read_bytes()
        require(type(expected_sha256) is str and hashlib.sha256(raw).hexdigest() == expected_sha256, 'budget_not_frozen')
        b = json.loads(raw)
        require(b.get('schema_version') == 1 and b.get('authorized_for_execution') is True
                and all(b.get(k) is True for k in ('price_verified','tokenizer_bound_verified','reasoning_total_bound_verified')), 'budget_not_authorized_or_proven')
        require(all(b.get(k) == v for k,v in profile.items()), 'prospective_budget_binding')
        model, effort, rate_in, rate_out = VOLUME_MODELS[profile['profile']]
        inp, out = (11264,2048) if profile['purpose'] == 'generation' else (8192,1024)
        require(b.get('model') == model and b.get('endpoint') == 'https://api.openai.com/v1/chat/completions'
                and b.get('request_options') == {'reasoning_effort': effort}
                and b.get('response_models') == [model], 'volume_model_options')
        require(b.get('input_tokens_per_request') == inp and b.get('output_tokens_per_request') == out
                and b.get('full_request_bytes') == inp - 1024 and b.get('message_bytes') == inp - 1024
                and b.get('framing_token_allowance') == 1024 and b.get('timeout_seconds') == 90, 'volume_token_limits')
        require(type(b.get('per_request_usd')) is str and type(b.get('max_total_usd')) is str, 'decimal_strings_required')
        unit, total = Decimal(b['per_request_usd']), Decimal(b['max_total_usd'])
        require(unit.is_finite() and total.is_finite() and unit == inp * rate_in + out * rate_out
                and total == unit * max_requests and 0 < total <= 2, 'volume_funding')
        expires = b.get('expires_at_epoch')
        require(type(expires) in (int,float) and time.time() < expires < float('inf'), 'budget_expired_or_invalid')
        require(callable(tokenizer), 'real_tokenizer_required')
        self.openai_native = True
        self._native_profile = profile['profile']
        self._native_limits = (inp - 1024, inp, inp - 1024)
        self._volume_output, self._volume_rates = out, (rate_in,rate_out)
        self.config, self.sha256, self.unit, self.total, self.tokenizer = b, expected_sha256, unit, total, tokenizer
        self.max_requests, self.wall, self.expires = max_requests, 300, expires
        self.cell_ids = frozenset(c['cell_id'] for c in cells)
        self._open_ledger(ledger_path)

    def _open_ledger(self, ledger_path):
        self.path = Path(ledger_path)
        if self.path.exists():
            raise BudgetError('budget_ledger_already_exists_no_retry')
        with sqlite3.connect(self.path) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE reservations(cell_id TEXT PRIMARY KEY, budget_sha TEXT NOT NULL, request_sha TEXT NOT NULL, amount TEXT NOT NULL, created REAL NOT NULL)')
        self.path.chmod(0o600)
        self.started = time.monotonic()

    def reserve(self, cell_id, request):
        if self.cell_ids is not None:
            require(type(cell_id) is str and cell_id in self.cell_ids, 'task_utility_cell_not_selected')
        if self.expires is not None:
            require(time.time() < self.expires, 'budget_expired')
        require(time.monotonic()-self.started < self.wall, 'wall_budget_exhausted')
        messages = request['messages']
        message_bytes = json_bytes(messages)
        require(len(message_bytes) <= (self._native_limits[2] if self.openai_native else self.config['message_bytes']), 'message_byte_limit')
        if self.openai_native:
            full_request = json_bytes(request)
            require(len(full_request) <= self._native_limits[0], 'full_request_byte_limit')
            tokens = len(full_request) + 1024
            if self.volume:
                required = {'model','messages','max_completion_tokens','reasoning_effort','stream'}
                optional = {'tools','tool_choice','parallel_tool_calls'} if self._native_profile == 'volume_luna6_none_v1' and self.config['purpose'] == 'generation' else set()
                require(required <= set(request) <= required | optional
                        and request.get('max_completion_tokens') == self._volume_output
                        and request.get('reasoning_effort') == self.config['request_options']['reasoning_effort']
                        and request.get('model') == self.config['model'] and type(request.get('stream')) is bool,
                        'request_configuration_changed')
                require(('tools' in request) == ('tool_choice' in request)
                        and ('parallel_tool_calls' not in request or request['parallel_tool_calls'] is True), 'volume_tools_options')
            else:
                require(request.get('max_tokens') == 2048 and request.get('temperature') == 0.7 and request.get('model') == 'gpt-4.1' and request.get('stream') is True and 'thinking' not in request, 'request_configuration_changed')
        else:
            tokens = self.tokenizer(messages)
            require(request.get('max_tokens') == 768 and request.get('temperature') == 0 and request.get('model') == self.config['model'] and request.get('thinking') == {'type':'disabled'}, 'request_configuration_changed')
        require(type(tokens) is int and 0 < tokens <= (self._native_limits[1] if self.openai_native else 9216), 'token_limit')
        if self.openai_native:
            if self.volume:
                require(Decimal(tokens) * self._volume_rates[0] + Decimal(self._volume_output) * self._volume_rates[1] <= self.unit, 'reservation_below_ratecard')
            else:
                require(self.unit == Decimal('0.04') and Decimal(tokens) * Decimal('0.000002') + Decimal(2048) * Decimal('0.000008') <= self.unit, 'reservation_below_ratecard')
        fingerprint = hashlib.sha256(json_bytes(request)).hexdigest()
        with sqlite3.connect(self.path) as db:
            db.execute('PRAGMA synchronous=FULL'); db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT amount FROM reservations').fetchall()
            require(len(rows) < self.max_requests and sum((Decimal(r[0]) for r in rows), Decimal(0)) + self.unit <= self.total, 'budget_exhausted')
            require(db.execute('SELECT 1 FROM reservations WHERE cell_id=?',(cell_id,)).fetchone() is None, 'cell_already_attempted')
            db.execute('INSERT INTO reservations VALUES(?,?,?,?,?)',(cell_id,self.sha256,fingerprint,str(self.unit),time.time()))
        return {'cost_reserved_usd':str(self.unit), 'input_token_upper_bound':tokens,
                'input_message_utf8_bytes':len(message_bytes), 'request_sha256':fingerprint}


class BoundedProviderClient:
    def __init__(self, budget, api_key, *, transport=None):
        self.budget = budget
        require(type(api_key) is str and bool(api_key.strip()), 'credential_missing')
        self._api_key = api_key
        self._transport = transport
        self.cell_id = None
        self.trace = None
        self.before_send = None

    async def agenerate(self, *, prompt, max_tokens, temperature=None, messages=None):
        require(self.cell_id is not None and type(prompt) is str, 'cell_not_bound')
        require(self.trace is None, 'one_send_per_cell')
        request = {'model':self.budget.config['model'], 'messages':[{'role':'user','content':prompt}],
                   'max_tokens':max_tokens,'temperature':temperature,'thinking':{'type':'disabled'},'stream':False}
        if self.budget.volume:
            require(temperature is None, 'volume_temperature_not_qualified')
            request = {'model':self.budget.config['model'], 'messages':[{'role':'user','content':prompt}],
                       'max_completion_tokens':max_tokens, 'reasoning_effort':self.budget.config['request_options']['reasoning_effort'], 'stream':False}
        if messages is not None:
            require(type(messages) is list and bool(messages) and all(
                type(item) is dict and type(item.get('role')) is str
                and type(item.get('content')) is str for item in messages), 'explicit_messages_invalid')
            # Preserve actual caller roles/content/history; never flatten to one user prompt.
            request['messages'] = json.loads(json.dumps(messages, ensure_ascii=False, allow_nan=False))
        # Authority revalidation is the last application operation before reservation/send.
        if self.before_send is not None:
            self.before_send()
        reservation = self.budget.reserve(self.cell_id, request)
        self.trace = {**reservation,'request':request,'provider_called':False,'response':None,
                      'status':'reserved','usage':None,'response_model':None,'output_tokens':None}
        try:
            async with httpx.AsyncClient(timeout=90, follow_redirects=False, trust_env=False,
                                         transport=self._transport) as client:
                self.trace['provider_called'] = True
                async with asyncio.timeout(90):
                    async with client.stream('POST',self.budget.config['endpoint'],headers={'Authorization':'Bearer '+self._api_key},json=request) as response:
                        chunks=[]; size=0
                        async for chunk in response.aiter_bytes():
                            size+=len(chunk);require(size<=262144,'response_size_limit');chunks.append(chunk)
                        self.trace['http_status']=response.status_code
                        response.raise_for_status()
                        value=json.loads(b''.join(chunks))
            self.trace.update(response=value, response_model=value.get('model'),usage=value.get('usage'))
            usage = value.get('usage',{})
            require(type(usage.get('prompt_tokens')) is int and 0 <= usage['prompt_tokens'] <= (self.budget._native_limits[1] if self.budget.volume else 9216), 'provider_input_usage_violation')
            require(type(usage.get('completion_tokens')) is int and 0 <= usage['completion_tokens'] <= (self.budget._volume_output if self.budget.volume else 768), 'provider_output_usage_violation')
            self.trace['output_tokens']=usage['completion_tokens']
            require(value.get('model') in self.budget.config['response_models'], 'response_model_mismatch')
            choice=value['choices'][0]
            if self.budget.volume:
                text=choice.get('message',{}).get('content')
                self.trace['finish_reason']=choice.get('finish_reason')
                if choice.get('finish_reason') == 'length' or not (type(text) is str and bool(text.strip())):
                    self.trace.update(status='incomplete', semantic_status='unknown',
                                      reason='output_truncated' if choice.get('finish_reason') == 'length' else 'empty_provider_response')
                    raise IncompleteProviderResponse(self.trace['reason'])
            require(choice.get('finish_reason') in ('stop','length'), 'unexpected_finish_reason')
            text=choice['message']['content']
            require(type(text) is str and bool(text.strip()), 'empty_provider_response')
            self.trace['status']='completed'
            return text
        except asyncio.CancelledError:
            self.trace.update(status='unavailable',reason='CancelledError')
            raise
        except (httpx.HTTPError, TimeoutError) as exc:
            self.trace.update(status='unavailable', reason=type(exc).__name__)
            raise
        except IncompleteProviderResponse:
            # Preserve the raw response, incomplete status and existing reservation.
            # Neither generation nor a judge may treat this as a valid answer.
            raise
        except Exception as exc:
            self.trace.update(status='error', reason=type(exc).__name__)
            raise
