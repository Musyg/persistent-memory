"""Public mode of the existing consumer runner: CaseMemory -> bounded provider.

No production consumer, LE/CG module, service, oracle, fallback or retry is used.
The provider transport and durable financial ledger remain bounded_provider's.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import itertools
import json
import os
from pathlib import Path
import time

from bounded_provider import BoundedProviderClient, json_bytes
from memory_packet import CaseMemory, Invalidated, POLICIES, RETRIEVAL_BUDGET, TEMPLATE, payload
from hermes_memory import core, typed_memory

CASE_FIELDS = {'case_id', 'workspace', 'task_text', 'query', 'as_of', 'conditions', 'evidence_kinds', 'documents', 'actions'}
DOC_FIELDS = {'doc_id', 'source_id', 'text', 'metadata', 'workspace'}
PERMUTATIONS = tuple(itertools.permutations(POLICIES))


def validate_cases(cases):
    if type(cases) is not list or not 0 < len(cases) <= 500:
        raise ValueError('case_limit')
    seen = set()
    for case in cases:
        if type(case) is not dict or set(case) - CASE_FIELDS:
            raise ValueError('unknown_case_field')
        for name in ('case_id', 'workspace', 'task_text', 'query'):
            if type(case.get(name)) is not str or not case[name] or len(case[name]) > 4096:
                raise ValueError('case_scalar_invalid')
        if case['case_id'] in seen:
            raise ValueError('duplicate_case_id')
        seen.add(case['case_id'])
        core.name(case['workspace'])
        if 'conditions' in case:
            typed_memory.conditions(case['conditions'])
        if 'as_of' in case:
            typed_memory.timestamp(case['as_of'])
        if 'evidence_kinds' in case and (type(case['evidence_kinds']) is not list or
                not all(type(kind) is str and kind in typed_memory.KINDS for kind in case['evidence_kinds'])):
            raise ValueError('evidence_kind_invalid')
        docs = case.get('documents')
        if type(docs) is not list or len(docs) > 24:
            raise ValueError('document_limit')
        ids, size = set(), 0
        for doc in docs:
            if type(doc) is not dict or set(doc) - DOC_FIELDS or not {'doc_id', 'source_id', 'text'} <= set(doc):
                raise ValueError('document_fields_invalid')
            if any(type(doc[name]) is not str or not doc[name] for name in ('doc_id', 'source_id', 'text')):
                raise ValueError('document_scalar_invalid')
            if doc['doc_id'] in ids:
                raise ValueError('duplicate_doc_id')
            ids.add(doc['doc_id'])
            core.name(doc['source_id'])
            size += len(doc['text'].encode())
            if type(doc.get('metadata', {})) is not dict:
                raise ValueError('metadata_invalid')
            if 'workspace' in doc and (type(doc['workspace']) is not str or not doc['workspace']):
                raise ValueError('document_workspace_invalid')
            core.name(doc.get('workspace', case['workspace']))
            typed_memory.metadata(doc.get('metadata', {}))
        if size > 131072:
            raise ValueError('source_byte_limit')
        if type(case.get('actions', [])) is not list:
            raise ValueError('action_invalid')
        for action in case.get('actions', []):
            if type(action) is not dict or set(action) != {'op', 'doc_id'} or action['op'] != 'revoke' or action['doc_id'] not in ids:
                raise ValueError('action_invalid')
    return cases


def load_inputs(path, expected_sha256):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('inputs_not_frozen')
    value = json.loads(raw)
    allowed = {'schema', 'synthetic', 'development_only', 'budget', 'cases'}
    if type(value) is not dict or set(value) != allowed or value['schema'] != 'persistent-memory.public-replay.inputs.v1' or value['synthetic'] is not True:
        raise ValueError('input_schema')
    if type(value['development_only']) is not bool or value['budget'] != RETRIEVAL_BUDGET:
        raise ValueError('retrieval_budget_changed')
    return validate_cases(value['cases'])


def append(path, row):
    # Same durable append as consumer_runner; no second financial ledger.
    with path.open('ab') as stream:
        os.chmod(path, 0o600)
        stream.write(json_bytes(row) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())


def execution_cells(cases, cells, mode):
    known = {case['case_id'] for case in cases}
    if cells is None:
        if mode != 'contract_test':
            raise ValueError('paid_execution_order_required')
        cells = [{'cell_id': case['case_id'] + '-' + policy, 'case_id': case['case_id'], 'policy_id': policy, 'repetition': 0}
                 for index, case in enumerate(cases) for policy in PERMUTATIONS[index % len(PERMUTATIONS)]]
    if type(cells) is not list or not cells:
        raise ValueError('execution_cells_required')
    # Keep Budget's pre-existing cell contract, rather than inventing a second
    # accounting identifier schema. Only this consumer maps arms to policies.
    if all(type(cell) is dict and set(cell) == {'cell_id', 'task_id', 'stage', 'arm'} for cell in cells):
        arms = {'memory_on': 'typed_fts_budgeted', 'memory_off': 'no_memory', 'simple_baseline': 'core_lexical_budgeted'}
        if any(cell['stage'] not in ('rep1', 'rep2', 'rep3') or cell['arm'] not in arms for cell in cells):
            raise ValueError('execution_cell_binding')
        cells = [{'cell_id': cell['cell_id'], 'case_id': cell['task_id'],
                  'policy_id': arms[cell['arm']], 'repetition': int(cell['stage'][-1]) - 1} for cell in cells]
    seen = set()
    for cell in cells:
        if type(cell) is not dict or set(cell) - {'cell_id', 'case_id', 'policy_id', 'repetition'} or not {'cell_id', 'case_id', 'policy_id'} <= set(cell):
            raise ValueError('execution_cell_fields')
        if type(cell['cell_id']) is not str or not 0 < len(cell['cell_id']) <= 256 or cell['cell_id'] in seen:
            raise ValueError('duplicate_or_invalid_cell_id')
        seen.add(cell['cell_id'])
        if cell['case_id'] not in known or cell['policy_id'] not in POLICIES or type(cell.get('repetition', 0)) is not int or not 0 <= cell.get('repetition', 0) <= 2:
            raise ValueError('execution_cell_binding')
    return cells


async def run_cells(source, cases, directory, provider_factory, *, mode, dataset_sha256, cells=None):
    validate_cases(cases)
    if mode not in ('contract_test', 'public_portable') or source is not None:
        raise ValueError('public_mode_invalid')
    plan = execution_cells(cases, cells, mode)
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    by_id = {case['case_id']: case for case in cases}
    attempts, preparation, bindings = [], [], []
    cancelled = False
    import asyncio
    for index, cell in enumerate(plan):
        case, policy = by_id[cell['case_id']], cell['policy_id']
        started = time.perf_counter_ns()
        row = {**cell, 'repetition': cell.get('repetition', 0), 'status': 'error', 'body': None,
               'context': None, 'evidence': [], 'reason': None, 'provider_called': False,
               'rendered_prompt_sha256': None, 'pre_authorized': None, 'post_authorized': None,
               'mode': mode, 'requested_max_tokens': 2048}
        append(directory / 'attempts.jsonl', {'event': 'intent', **cell, 'mode': mode})
        memory = provider = None
        try:
            if cancelled:
                raise asyncio.CancelledError()
            if policy != 'no_memory':
                memory = CaseMemory(None, directory / ('cell-' + str(index)), case, typed=policy == 'typed_fts_budgeted')
                preparation.append({**cell, 'setup_ns': memory.setup_ns, 'sync_ns': memory.sync_ns, 'sync': memory.sync})
                bindings.extend({**cell, 'doc_id': doc_id, **binding} for doc_id, binding in memory.bindings.items())
            packet = memory.retrieve(policy) if memory else {'policy_id': policy, 'evidence': [], 'context': '', 'checkpoint': None}
            row.update(context=packet['context'], evidence=packet['evidence'], checkpoint=packet['checkpoint'])
            rendered = TEMPLATE.format(payload=payload(case, packet))
            row['rendered_prompt_sha256'] = hashlib.sha256(rendered.encode()).hexdigest()
            provider = provider_factory(cell['cell_id'])
            if mode == 'public_portable' and not isinstance(provider, BoundedProviderClient):
                raise ValueError('real_bounded_transport_required')
            provider.cell_id = cell['cell_id']
            factory_before_send = provider.before_send
            def precheck():
                row['pre_authorized'] = memory.revalidate(packet) if memory else True
            def before_send():
                # Preserve Root's factory-installed admission hook. Capture its
                # value before assignment, so this cannot call itself recursively.
                if factory_before_send is not None:
                    factory_before_send()
                precheck()
            provider.before_send = before_send
            precheck()
            body = await provider.agenerate(prompt=rendered, max_tokens=2048, temperature=None,
                                           messages=[{'role': 'user', 'content': rendered}])
            # A length-truncated generation is not a completed business answer.
            trace = getattr(provider, 'trace', None) or {}
            choices = (trace.get('response') or {}).get('choices') or []
            if choices and choices[0].get('finish_reason') != 'stop':
                raise ValueError('generation_not_finished')
            if type(body) is not str or not body.strip():
                raise ValueError('empty_provider_response')
            try:
                row['post_authorized'] = memory.revalidate(packet) if memory else True
            except Exception as exc:
                row['post_authorized'] = False
                append(directory / 'quarantine.jsonl', {'cell_id': cell['cell_id'], 'content': body, 'reason': type(exc).__name__})
                raise Invalidated('authority_changed_after_generation') from exc
            row.update(status='completed', body=body)
        except asyncio.CancelledError:
            cancelled = True
            row.update(status='unavailable', reason='run_cancelled_no_further_sends')
        except Invalidated as exc:
            called = bool((getattr(provider, 'trace', None) or {}).get('provider_called'))
            row.update(status='invalidated_during_generation' if called else 'unavailable', reason=str(exc))
        except Exception as exc:
            trace = getattr(provider, 'trace', None) or {}
            status = trace.get('status')
            row.update(status=status if status in ('unavailable', 'incomplete') else 'error',
                       reason=type(exc).__name__ + ':' + str(exc)[:160])
            if status == 'incomplete':
                row['semantic_status'] = 'unknown'
        if provider is not None:
            trace = getattr(provider, 'trace', None) or {}
            row['provider_called'] = trace.get('provider_called', False)
            request = trace.get('request')
            if request:
                actual = request.get('messages')
                expected = [{'role': 'user', 'content': rendered}]
                if actual != expected:
                    row.update(status='error', reason='provider_prompt_mismatch', body=None)
            for key in ('cost_reserved_usd', 'input_token_upper_bound', 'output_tokens', 'usage', 'response_model'):
                row[key] = trace.get(key)
            append(directory / 'request-response.jsonl', {'cell_id': cell['cell_id'], **trace})
        row['total_ns'] = time.perf_counter_ns() - started
        append(directory / 'attempts.jsonl', {'event': 'result', **row})
        attempts.append(row)
    report = {'schema': 'persistent-memory.public-replay.report.v1', 'dataset_sha256': dataset_sha256,
              'target': {'package': 'hermes-memory-core', 'version': importlib.metadata.version('hermes-memory-core'),
                         'consumer': 'portable_pre_retrieval_single_generation', 'full_hermes_parity_claimed': False},
              'mode': mode, 'attempts': attempts, 'bindings': bindings, 'preparation': preparation,
              'execution_cells': plan, 'oracle_read': False, 'provider_retries': 0, 'promoted': False}
    (directory / 'report.json').write_bytes(json_bytes(report) + b'\n')
    return report
