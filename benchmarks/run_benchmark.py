"""Small synthetic index/revalidation exercise, not a production speed claim."""
import json
import hashlib
import math
from pathlib import Path
import random
import statistics
import tempfile
import time

from hermes_memory import Authority, Memory
from hermes_memory.typed_memory import TypedMemory


def main(documents=24, repetitions=10, seed=0, *, volume=False):
    if not (type(documents) is int and 1 <= documents <= 5000
            and type(repetitions) is int and 1 <= repetitions <= 100000
            and type(seed) is int and 0 <= seed < 2 ** 64):
        raise ValueError('Expected documents 1..5000, repetitions 1..100000 and seed 0..2^64-1')
    operations = {'typed.put': 0, 'typed.sync': 0, 'typed.search': 0,
                  'memory.read': 0, 'memory.revoke_source': 0}
    generator = random.Random(seed)
    query_digest = hashlib.sha256()
    queried = set()
    statuses = {}
    hits = omissions = unexpected_items = truncated_queries = 0
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        authority = Authority.create(root / 'authority.db', root / 'anchor.json')
        memory = Memory.create(root / 'memory.db', authority)
        typed = TypedMemory(memory, root / 'index.db')
        refs = []
        ingest_started = time.perf_counter()
        for index in range(documents):
            text = 'Synthetic copper item number ' + str(index)
            if volume:
                text += ' token' + format(index, '06d')
            refs.append(typed.put('example', 'note-' + str(index),
                                  text,
                                  {'evidence_kind': 'observation'})['ref'])
            operations['typed.put'] += 1
        ingest_seconds = time.perf_counter() - ingest_started
        sync_started = time.perf_counter()
        typed.sync('example')
        operations['typed.sync'] += 1
        initial_sync_seconds = time.perf_counter() - sync_started
        timings = []
        for _ in range(repetitions):
            selected = generator.randrange(documents) if volume else None
            query = 'token' + format(selected, '06d') if volume else 'copper'
            if volume:
                query_digest.update((query + '\n').encode('ascii'))
                queried.add(selected)
            start = time.perf_counter()
            result = typed.search('example', query, top_k=5, max_context_chars=200)
            timings.append(time.perf_counter() - start)
            operations['typed.search'] += 1
            assert len(result['context']) <= 200
            if volume:
                statuses[result['status']] = statuses.get(result['status'], 0) + 1
                found = any(item['ref'] == refs[selected] for item in result['items'])
                hits += int(found)
                omissions += int(not found)
                unexpected_items += sum(item['ref'] != refs[selected] for item in result['items'])
                truncated_queries += int(result.get('coverage', {}).get('candidate_truncated', False))
            else:
                assert result['status'] == 'completed'
            for item in result['items']:
                assert memory.read(item['ref'])['allowed']
                operations['memory.read'] += 1
        memory.revoke_source('example', 'note-0', 'example-revoke-0')
        operations['memory.revoke_source'] += 1
        revocation_query = 'token000000' if volume else 'copper'
        stale = typed.search('example', revocation_query)
        operations['typed.search'] += 1
        assert stale['status'] != 'completed'
        resync_started = time.perf_counter()
        typed.sync('example')
        operations['typed.sync'] += 1
        revocation_sync_seconds = time.perf_counter() - resync_started
        after = typed.search('example', revocation_query)
        operations['typed.search'] += 1
        assert all(item['ref'] != refs[0] for item in after['items'])
        if volume:
            assert stale['status'] == 'index_stale'
            assert after['status'] == 'completed' and after['items'] == []
            disk_bytes = sum(path.stat().st_size for path in root.rglob('*') if path.is_file())
    report = {'synthetic_documents': documents, 'repetitions': repetitions,
              'median_seconds': statistics.median(timings), 'max_seconds': max(timings),
              'revocation_checked': True, 'cold_cache_controlled': False,
              'general_speed_superiority_claimed': False}
    if volume:
        import importlib.metadata
        import platform
        import resource
        import sqlite3
        import sys
        try:
            package_version = importlib.metadata.version('hermes-memory-core')
        except importlib.metadata.PackageNotFoundError:
            package_version = None
        report.update({
            'mode': 'synthetic_typed_volume', 'seed': seed,
            'query_kind': 'unique_synthetic_lexical_token',
            'query_schedule_sha256': query_digest.hexdigest(), 'distinct_queries': len(queried),
            'retrieval_trials': repetitions, 'expected_hits': hits, 'omissions': omissions,
            'unexpected_items': unexpected_items, 'status_counts': statuses,
            'candidate_truncated_queries': truncated_queries,
            'oracle_passed': hits == repetitions and unexpected_items == 0
                             and truncated_queries == 0 and statuses == {'completed': repetitions},
            'p50_seconds': statistics.median(timings),
            'p95_seconds': sorted(timings)[math.ceil(0.95 * len(timings)) - 1],
            'p95_method': 'nearest_rank',
            'mean_seconds': statistics.mean(timings),
            'latency_scope': 'typed.search only; explicit benchmark memory.read checks excluded',
            'ingest_seconds': ingest_seconds, 'initial_sync_seconds': initial_sync_seconds,
            'revocation_sync_seconds': revocation_sync_seconds,
            'public_method_calls': operations, 'public_method_calls_total': sum(operations.values()),
            'operation_scope': 'explicit benchmark calls only; initialization and internal calls excluded',
            'initialization_calls': {'Authority.create': 1, 'Memory.create': 1, 'TypedMemory': 1},
            'disk_bytes_after_revocation_sync': disk_bytes,
            'rss_peak_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1024 if sys.platform == 'linux' else 1),
            'rss_scope': 'process lifetime high-water mark; not incremental memory usage',
            'python_version': platform.python_version(), 'sqlite_version': sqlite3.sqlite_version,
            'platform': platform.platform(), 'package_version': package_version,
            'API_calls_requested_by_benchmark': 0,
            'provider_requests': 0,
            'ranking_quality_evaluated': False, 'independent_business_tasks': 0,
        })
    print(json.dumps(report, indent=2))
    return report



def transition_trajectories(trajectories=3000, seed=20261021, batch_size=50):
    """Seeded permutations of existing CoreScenarios, not independent clients."""
    from collections import Counter
    from unittest.mock import patch
    import sqlite3
    from hermes_memory import MemoryError

    if not (type(trajectories) is int and 1 <= trajectories <= 3000
            and type(seed) is int and 0 <= seed < 2 ** 64
            and type(batch_size) is int and 1 <= batch_size <= 100):
        raise ValueError('Expected 1..3000 trajectories, uint64 seed, batch 1..100')
    generator = random.Random(seed)
    families = ['revision', 'revoke_late', 'restore', 'outbox', 'anchor_gap', 'isolation']
    schedule = [families[i % len(families)] for i in range(trajectories)]
    generator.shuffle(schedule)
    calls, checks, rows = Counter(), Counter(), []
    started = time.perf_counter()

    def call(obj, method, *args, **kwargs):
        calls[type(obj).__name__ + '.' + method] += 1
        return getattr(obj, method)(*args, **kwargs)

    def allowed(memory, refs, expected):
        for ref in refs:
            decision = call(memory, 'read', ref)
            checks['read_invariants'] += 1
            assert decision['allowed'] is expected, decision

    for batch_start in range(0, trajectories, batch_size):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            authority = Authority.create(root / 'authority.db', root / 'anchor.json')
            memory = Memory.create(root / 'content.db', authority)
            calls['Authority.create'] += 1
            calls['Memory.create'] += 1
            for index in range(batch_start, min(batch_start + batch_size, trajectories)):
                family, depth = schedule[index], generator.randrange(1, 4)
                workspace, source_id = 'synthetic', 'source-' + str(index)
                text = 'Synthetic trajectory ' + str(index)
                source = call(memory, 'register_source', workspace, source_id, text)['ref']
                allowed(memory, [source], True)
                independent = call(memory, 'register_source', workspace, 'independent-' + str(index), 'independent')['ref']
                dependents, parent = [], source
                allowed(memory, [source, independent], True)
                for level in range(depth):
                    parent = call(memory, 'derive', workspace, 'derived-' + str(index) + '-' + str(level),
                                  text, 'fact', [{'ref': parent, 'relation': 'derives'}],
                                  call(memory, 'checkpoint')['epoch'])['ref']
                    dependents.append(parent)
                    allowed(memory, [source, independent, *dependents], True)
                epoch = call(memory, 'checkpoint')['epoch']
                if family == 'revision':
                    current = call(memory, 'register_source', workspace, source_id, text + ' revised',
                                   expected_version=source['version_id'])['ref']
                    allowed(memory, [source, *dependents], False)
                    allowed(memory, [current, independent], True)
                elif family == 'isolation':
                    try:
                        call(memory, 'derive', 'other', 'cross-' + str(index), text, 'fact',
                             [{'ref': source, 'relation': 'derives'}], epoch)
                    except MemoryError:
                        checks['expected_rejections'] += 1
                    else:
                        raise AssertionError('Cross-workspace dependency admitted')
                    allowed(memory, [source, independent, *dependents], True)
                else:
                    if family == 'restore':
                        backup = root / ('backup-' + str(index) + '.db')
                        call(memory, 'backup', backup)
                    if family == 'outbox':
                        try:
                            call(memory, 'drain_outbox', fail_after_projection=True)
                        except MemoryError:
                            checks['expected_faults'] += 1
                        else:
                            raise AssertionError('Projection crash not injected')
                        allowed(memory, [source, independent, *dependents], True)
                        call(memory, 'drain_outbox')
                        allowed(memory, [source, independent, *dependents], True)
                        call(memory, 'drain_outbox')
                        allowed(memory, [source, independent, *dependents], True)
                    if family == 'anchor_gap':
                        with patch('hermes_memory.core.atomic_json', side_effect=OSError('synthetic anchor outage')):
                            try:
                                call(memory, 'revoke_source', workspace, source_id, 'revoke-' + str(index))
                            except OSError:
                                checks['expected_faults'] += 1
                            else:
                                raise AssertionError('Anchor outage not injected')
                        allowed(memory, [source, independent, *dependents], False)
                        with sqlite3.connect(authority.path) as connection:
                            connection.row_factory = sqlite3.Row
                            trusted = authority._checkpoint(connection)
                        calls['Authority._checkpoint_trusted_repair_only'] += 1
                        call(authority, 'recover_anchor', trusted)
                    else:
                        call(memory, 'revoke_source', workspace, source_id, 'revoke-' + str(index))
                    allowed(memory, [source, *dependents], False)
                    allowed(memory, [independent], True)
                    if family == 'revoke_late':
                        try:
                            call(memory, 'derive', workspace, 'late-' + str(index), text, 'fact',
                                 [{'ref': source, 'relation': 'derives'}], epoch)
                        except MemoryError:
                            checks['expected_rejections'] += 1
                        else:
                            raise AssertionError('Late revoked write admitted')
                        allowed(memory, [source, *dependents], False)
                        allowed(memory, [independent], True)
                    if family == 'restore':
                        restored = Memory.open(backup, authority)
                        calls['Memory.open'] += 1
                        allowed(restored, [source, independent, *dependents], False)
                        call(restored, 'restore_verify', call(authority, 'checkpoint'))
                        allowed(restored, [source, *dependents], False)
                        allowed(restored, [independent], True)
                checks['completed_trajectories'] += 1
                assert sum(calls.values()) <= 100000, 'explicit operation cap'
                rows.append({'index': index, 'family': family, 'dependency_depth': depth, 'passed': True})
    report = {'mode': 'seeded_existing_core_scenario_transitions', 'seed': seed,
              'trajectories': trajectories, 'completed': len(rows), 'batch_size': batch_size,
              'database_batches': math.ceil(trajectories / batch_size),
              'family_counts': dict(Counter(schedule)), 'checks': dict(checks),
              'explicit_method_calls': dict(calls), 'explicit_method_calls_total': sum(calls.values()),
              'call_scope': 'explicit harness calls including initialization; internal SQLite work excluded',
              'generated_cases': rows, 'elapsed_seconds': time.perf_counter() - started,
              'provider_requests': 0, 'independent_clients': 0, 'business_tasks': 0,
              'oracle_passed': len(rows) == trajectories}
    print(json.dumps(report, indent=2))
    return report


def lance_hybrid_demo():
    """Local synthetic binding/currentness exercise; no learned ranking claim."""
    import importlib.metadata
    import lancedb
    import pyarrow as pa
    from hermes_memory.core import Ref
    from hermes_memory.typed_memory import decode

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        authority = Authority.create(root / 'authority.db', root / 'anchor.json')
        memory = Memory.create(root / 'memory.db', authority)
        typed = TypedMemory(memory, root / 'index.db')
        workspace = 'example'
        texts = [
            'Synthetic copper preference concise.',
            'Synthetic copper note to revoke.',
            'Synthetic copper preference old.',
            'Synthetic copper unrelated note.',
        ]
        vectors = [[1.0, 0.0, 0.0], [0.9, 0.1, 0.0],
                   [0.8, 0.2, 0.0], [0.0, 0.0, 1.0]]
        refs = [typed.put(workspace, 'note-' + str(index), text,
                          {'evidence_kind': 'observation'})['ref']
                for index, text in enumerate(texts)]
        typed.sync(workspace)
        rows = [{'text': text, 'vector': vector,
                 'ref': json.dumps(ref, sort_keys=True)}
                for text, vector, ref in zip(texts, vectors, refs)]
        schema = pa.schema([('text', pa.string()),
                            ('vector', pa.list_(pa.float32(), 3)),
                            ('ref', pa.string())])
        db = lancedb.connect(str(root / 'lance'))
        table = db.create_table('synthetic', data=rows, schema=schema)
        table.create_fts_index('text', use_tantivy=False)
        projection_checkpoint = memory.checkpoint()

        def current_query(candidate_limit):
            checkpoint = memory.checkpoint()
            assert checkpoint == projection_checkpoint, 'explicit_refresh_required'
            start = time.perf_counter()
            candidates = (table.search(query_type='hybrid',
                                       vector_column_name='vector', fts_columns='text')
                          .vector([1.0, 0.0, 0.0]).text('copper')
                          .limit(candidate_limit).to_list())
            elapsed = time.perf_counter() - start
            candidate_refs = [Ref(**json.loads(row['ref'])).to_dict()
                              for row in candidates]
            assert all(ref['workspace'] == workspace for ref in candidate_refs)
            decisions = memory.validate(candidate_refs)['decisions']
            assert len(decisions) == len(candidate_refs)
            items, exclusions = [], []
            for ref, decision in zip(candidate_refs, decisions):
                assert decision['ref'] == ref
                if not decision['allowed']:
                    assert decision['reason'] not in {
                        'authority_or_store_unavailable', 'content_missing'}
                    exclusions.append({'ref': ref, 'reason': decision['reason']})
                    continue
                envelope = decode(decision['content'])
                assert envelope is not None
                items.append({'ref': ref, 'text': envelope['text']})
            context = '\n\n'.join(item['text'] for item in items)
            assert len(context) <= 200
            assert memory.checkpoint() == checkpoint, 'concurrent_authority_change'
            return {'candidate_count': len(candidates), 'items': items,
                    'context': context, 'context_chars': len(context),
                    'exclusions': exclusions, 'seconds': elapsed}

        before = current_query(4)
        assert len(before['items']) == 4
        corrected = typed.put(workspace, 'note-2',
                              'Synthetic copper preference corrected.',
                              {'evidence_kind': 'observation'},
                              expected_version=refs[2]['version_id'])['ref']
        memory.revoke_source(workspace, 'note-1', 'example-revoke-1')
        stale = typed.search(workspace, 'copper')
        assert stale['status'] == 'index_stale'
        assert memory.checkpoint() != projection_checkpoint
        typed.sync(workspace)
        table.add([{'text': 'Synthetic copper preference corrected.',
                    'vector': [0.8, 0.2, 0.0],
                    'ref': json.dumps(corrected, sort_keys=True)}])
        table.create_fts_index('text', use_tantivy=False, replace=True)
        projection_checkpoint = memory.checkpoint()
        after = current_query(5)
        admitted = [item['ref'] for item in after['items']]
        assert after['candidate_count'] == 5 and len(admitted) == 3
        assert corrected in admitted and refs[0] in admitted and refs[3] in admitted
        assert refs[1] not in admitted and refs[2] not in admitted
        assert {item['reason'] for item in after['exclusions']} == {
            'source_revoked', 'version_not_current'}
    print(json.dumps({
        'mode': 'synthetic_lance_hybrid_currentness_demo',
        'lancedb_version': importlib.metadata.version('lancedb'),
        'pyarrow_version': importlib.metadata.version('pyarrow'),
        'synthetic_sources': 4, 'stored_projection_rows_after': 5,
        'vector_dimensions': 3, 'binding': 'explicit_vector_and_text',
        'embedding_function_configured': False, 'fallback_implemented': False,
        'API_calls_requested_by_demo': 0, 'downloads_requested_by_demo': 0,
        'models_requested_by_demo': 0, 'stale_index_refused': True,
        'revocation_checked': True, 'superseded_version_excluded': True,
        'before': before, 'after': after, 'ranking_quality': 'not_evaluated',
        'cold_cache_controlled': False, 'general_speed_superiority_claimed': False,
    }, indent=2))

COMPARISON_SCENARIOS = ('Q01', 'Q02', 'Q03', 'Q04', 'Q05', 'Q06', 'Q07', 'Q09', 'Q10', 'Q12')
COMPARISON_ARMS = ('hermes', 'sqlite_retained', 'sqlite_snapshot_local')
COMPARISON_SEED = 20261022


def _comparison_support():
    """Load the adjacent support explicitly, including under Python -I.

    Historical modes never call this function or import the support module.
    """
    import importlib.util
    import sys
    path = Path(__file__).with_name('lifecycle_reference.py').resolve()
    name = '_persistent_memory_lifecycle_reference'
    existing = sys.modules.get(name)
    if existing is not None:
        if Path(existing.__file__).resolve() != path:
            raise ImportError('Lifecycle support module path conflict')
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if sys.modules.get(name) is module:
            del sys.modules[name]
        raise
    return module


def comparison_schedule(fixture, variants=10, seed=COMPARISON_SEED):
    """Validate external expectations and shuffle once, independently of backends."""
    if type(variants) is not int or not 1 <= variants <= 10 or type(seed) is not int or not 0 <= seed < 2 ** 64:
        raise ValueError('Expected variants 1..10 and uint64 seed')
    if type(fixture.get('schema_version')) is not int or fixture['schema_version'] != 1 or type(fixture.get('scenarios')) is not list:
        raise ValueError('Invalid lifecycle fixture schema')
    scenarios = fixture['scenarios']
    if len(scenarios) != 10 or {s.get('id') for s in scenarios} != set(COMPARISON_SCENARIOS):
        raise ValueError('Expected the ten frozen matched scenarios')
    allowed_ops = {'source', 'derive', 'checkpoint', 'read', 'revoke', 'backup', 'restore', 'verify_restore', 'reopen'}
    schedule = []
    case_ids = set()
    for scenario in scenarios:
        if type(scenario.get('variants')) is not list or len(scenario['variants']) != 10:
            raise ValueError('Expected ten explicit variants per scenario')
        for variant in scenario['variants']:
            case_id = scenario['id'] + ':' + str(variant['id'])
            if case_id in case_ids:
                raise ValueError('Duplicate comparison case identifier')
            case_ids.add(case_id)
            operations = variant.get('operations')
            if type(operations) is not list or not operations:
                raise ValueError('Expected explicit operations')
            symbols = {'ref': set(), 'checkpoint': set(), 'backup': set()}
            for operation in operations:
                op = operation.get('op')
                if op not in allowed_ops:
                    raise ValueError('Unknown lifecycle operation')
                if op in {'source', 'derive'}:
                    if type(operation.get('text')) is not str:
                        raise ValueError('Source and derivative text must be exact strings')
                    if operation.get('expected_version') is not None and operation['expected_version'] not in symbols['ref']:
                        raise ValueError('Unknown expected version symbol')
                if op == 'derive':
                    if operation.get('kind', 'fact') != 'fact' or operation.get('checkpoint') not in symbols['checkpoint']:
                        raise ValueError('Unknown checkpoint or unsupported derivative kind')
                    for dependency in operation['dependencies']:
                        if dependency['ref'] not in symbols['ref'] or dependency['relation'] not in {'derives', 'indexes', 'cites', 'navigates'}:
                            raise ValueError('Unknown dependency symbol or relation')
                if op == 'read':
                    if operation.get('ref') not in symbols['ref']:
                        raise ValueError('Unknown read symbol')
                    for expectation in [operation.get('expect'), *operation.get('expect_by_profile', {}).values()]:
                        if type(expectation) is not dict or type(expectation.get('allowed')) is not bool:
                            raise ValueError('Read requires an explicit boolean oracle')
                        if expectation['allowed'] and type(expectation.get('text')) is not str:
                            raise ValueError('Allowed read requires exact text')
                        if not expectation['allowed'] and (expectation.get('text_absent') is not True or expectation.get('text') is not None):
                            raise ValueError('Denied read must explicitly forbid content')
                if op == 'restore' and operation.get('backup') not in symbols['backup']:
                    raise ValueError('Unknown backup symbol')
                if op == 'verify_restore' and operation.get('checkpoint') not in symbols['checkpoint']:
                    raise ValueError('Unknown restore checkpoint')
                if 'expect_error' in operation and operation['expect_error'] not in {
                        'version_conflict', 'stale_epoch', 'dependency_invalid', 'scope_mismatch',
                        'source_revoked', 'event_id_conflict', 'restore_fresh_checkpoint_required'}:
                    raise ValueError('Unknown expected rejection class')
                if 'as' in operation and op in {'source', 'derive', 'checkpoint', 'backup'}:
                    group = 'checkpoint' if op == 'checkpoint' else 'backup' if op == 'backup' else 'ref'
                    if operation['as'] in symbols[group]:
                        raise ValueError('Duplicate result symbol')
                    if 'expect_error' not in operation:
                        symbols[group].add(operation['as'])
            if variant in scenario['variants'][:variants]:
                schedule.append({'case_id': case_id, 'scenario': scenario['id'], 'variant': variant['id'], 'operations': operations})
    random.Random(seed).shuffle(schedule)
    return schedule


def normalize_lifecycle_rejection(error):
    """Only recognized semantic exceptions count as an expected rejection."""
    from hermes_memory.core import MemoryError
    Rejected = _comparison_support().Rejected
    if not isinstance(error, (MemoryError, Rejected)):
        return None
    reason = str(error)
    if reason in {'version_not_current', 'unknown_ref', 'dependency_cycle_or_depth'}:
        return 'dependency_invalid'
    if reason in {'version_conflict', 'stale_epoch', 'dependency_invalid', 'scope_mismatch',
                  'source_revoked', 'event_id_conflict', 'restore_fresh_checkpoint_required'}:
        return reason
    return None


def _comparison_read_matches(actual, expected):
    if type(actual.get('allowed')) is not bool or actual['allowed'] != expected['allowed']:
        return False
    if expected['allowed']:
        return actual.get('content') == expected['text']
    return actual.get('content') is None


def _comparison_normalized_actual(value, refs):
    """Keep raw outcomes too; remove generated tokens only from the parity view."""
    if isinstance(value, list):
        return [_comparison_normalized_actual(item, refs) for item in value]
    if isinstance(value, dict):
        if set(value) == {'workspace', 'artifact_id', 'version_id'}:
            symbol = next((symbol for symbol, ref in refs.items() if ref == value), 'UNBOUND')
            return {'symbol': symbol, 'workspace': value['workspace'], 'artifact_id': value['artifact_id']}
        if 'generation' in value and 'epoch' in value:
            return {'epoch': value['epoch']}
        return {key: _comparison_normalized_actual(item, refs) for key, item in value.items()}
    return value


def comparison_deterministic_view(cases):
    return [{**{key: value for key, value in case.items() if key != 'observations'},
             'observations': [{key: value for key, value in observation.items() if key != 'actual'}
                              for observation in case['observations']]} for case in cases]


def replay_comparison_case(adapter, case, profile):
    """Single declarative executor: expected values never enter an adapter call."""
    refs, checkpoints, backups, receipts = {}, {}, {}, {}
    observations = []
    for index, operation in enumerate(case['operations']):
        op = operation['op']
        observation = {'index': index, 'op': op, 'input': operation,
                       'oracle_passed': False, 'profile_passed': False}
        expected_error = operation.get('expect_error')
        try:
            if op == 'source':
                previous = operation.get('expected_version')
                result = adapter.put_source(operation['workspace'], operation['id'], operation['text'],
                                            refs[previous]['version_id'] if previous is not None else None)
            elif op == 'derive':
                previous = operation.get('expected_version')
                dependencies = [{'ref': refs[d['ref']], 'relation': d['relation']} for d in operation['dependencies']]
                result = adapter.derive(operation['workspace'], operation['id'], operation['text'], dependencies,
                                        checkpoints[operation['checkpoint']],
                                        refs[previous]['version_id'] if previous is not None else None)
            elif op == 'checkpoint':
                result = adapter.checkpoint()
                checkpoints[operation['as']] = result
            elif op == 'read':
                result = adapter.read(refs[operation['ref']])
            elif op == 'revoke':
                result = adapter.revoke(operation['workspace'], operation['id'], operation['event'])
                identity = (operation['workspace'], operation['id'], operation['event'])
                receipt = {key: result[key] for key in ('event_id', 'epoch', 'registered')}
                observation['idempotence_checked'] = identity in receipts
                observation['idempotence_passed'] = identity not in receipts or receipts[identity] == receipt
                receipts[identity] = receipt
            elif op == 'backup':
                backups[operation['as']] = adapter.backup()
                result = {'saved': True}
            elif op == 'restore':
                adapter.restore(backups[operation['backup']])
                result = {'restored': True}
            elif op == 'verify_restore':
                result = adapter.verify_restore(checkpoints[operation['checkpoint']])
            elif op == 'reopen':
                adapter.reopen()
                result = {'reopened': True}
            else:
                raise ValueError('Unknown lifecycle operation')
            observation['actual'] = result
            if op in {'source', 'derive'} and not expected_error:
                refs[operation['as']] = result['ref']
            passed = expected_error is None and observation.get('idempotence_passed', True)
            if op == 'revoke':
                passed = passed and result.get('registered') is True and result.get('event_id') == operation['event']
            if op == 'verify_restore':
                passed = passed and result.get('ready') is True
            if op == 'read':
                passed = passed and _comparison_read_matches(result, operation['expect'])
                profile_expected = operation.get('expect_by_profile', {}).get(profile, operation['expect'])
                observation['profile_passed'] = _comparison_read_matches(result, profile_expected)
            else:
                observation['profile_passed'] = passed
            observation['oracle_passed'] = passed
        except Exception as error:
            normalized = normalize_lifecycle_rejection(error)
            observation['actual'] = {'rejected': normalized, 'exception': type(error).__name__, 'message': str(error)}
            observation['oracle_passed'] = expected_error is not None and normalized == expected_error
            observation['profile_passed'] = observation['oracle_passed']
            if not observation['oracle_passed']:
                observation['unexpected_error'] = True
        labels = dict(refs)
        if op in {'source', 'derive'} and 'ref' in observation['actual']:
            labels[operation['as']] = observation['actual']['ref']
        observation['normalized_actual'] = _comparison_normalized_actual(observation['actual'], labels)
        observations.append(observation)
        if observation.get('unexpected_error'):
            break  # Remaining events are explicitly unexecuted, never passed.
    return {'case_id': case['case_id'], 'scenario': case['scenario'], 'variant': case['variant'],
            'planned_operations': len(case['operations']), 'observations': observations,
            'completed': len(observations) == len(case['operations']),
            'oracle_passed': len(observations) == len(case['operations']) and all(o['oracle_passed'] for o in observations),
            'profile_passed': len(observations) == len(case['operations']) and all(o['profile_passed'] for o in observations)}


def summarize_comparison(cases):
    """Recomputable counts with separate safety and availability denominators."""
    from collections import Counter
    counts = Counter({key: 0 for key in (
        'operations', 'unexpected_errors', 'unexecuted_operations', 'read_checks',
        'valid_read_checks', 'valid_reads_exact', 'valid_reads_unavailable',
        'valid_reads_wrong_content', 'denied_read_checks', 'forbidden_reads_exposed',
        'expected_rejections', 'matched_rejections', 'forbidden_writes_accepted',
        'late_write_checks', 'late_writes_accepted', 'restore_events', 'restore_events_succeeded',
        'verify_restore_events', 'verify_restore_events_succeeded', 'reopen_events',
        'reopen_events_succeeded', 'idempotence_checks', 'idempotence_failures', 'initialization_errors')})
    counts.update(cases=len(cases), completed_cases=sum(c['completed'] for c in cases),
                     oracle_passed_cases=sum(c['oracle_passed'] for c in cases),
                     profile_passed_cases=sum(c['profile_passed'] for c in cases))
    for case in cases:
        counts['initialization_errors'] += 'initialization_error' in case
        counts['unexpected_errors'] += 'initialization_error' in case
        counts['unexecuted_operations'] += case['planned_operations'] - len(case['observations'])
        for observation in case['observations']:
            counts['operations'] += 1
            counts['unexpected_errors'] += bool(observation.get('unexpected_error'))
            operation, actual = observation['input'], observation['actual']
            if observation['op'] == 'read':
                expected = operation['expect']
                category = expected.get('category', 'unspecified')
                counts['read_checks'] += 1
                counts[category + '_read_checks'] += 1
                if expected['allowed']:
                    counts['valid_read_checks'] += 1
                    counts['valid_reads_exact'] += _comparison_read_matches(actual, expected)
                    counts[category + '_reads_exact'] += _comparison_read_matches(actual, expected)
                    counts['valid_reads_unavailable'] += actual.get('allowed') is not True
                    counts['valid_reads_wrong_content'] += actual.get('allowed') is True and actual.get('content') != expected['text']
                else:
                    counts['denied_read_checks'] += 1
                    exposed = actual.get('allowed') is True or actual.get('content') is not None
                    counts['forbidden_reads_exposed'] += exposed
                    counts[category + '_reads_exposed'] += exposed
            if observation['op'] in {'restore', 'verify_restore', 'reopen'}:
                counts[observation['op'] + '_events'] += 1
                counts[observation['op'] + '_events_succeeded'] += observation['oracle_passed']
            if operation.get('expect_error'):
                counts['expected_rejections'] += 1
                counts['matched_rejections'] += observation['oracle_passed']
                if observation['op'] in {'source', 'derive'} and 'rejected' not in actual:
                    counts['forbidden_writes_accepted'] += 1
                if observation['op'] == 'derive' and operation['expect_error'] in {'stale_epoch', 'source_revoked', 'dependency_invalid'}:
                    counts['late_write_checks'] += 1
                    counts['late_writes_accepted'] += 'rejected' not in actual
            if observation.get('idempotence_checked'):
                counts['idempotence_checks'] += 1
                counts['idempotence_failures'] += not observation['idempotence_passed']
    return dict(sorted(counts.items()))


def compare_transitions(fixture_path=None, variants=10, seed=COMPARISON_SEED, *,
                        arm_order=COMPARISON_ARMS, adapter_factories=None, emit=True):
    support = _comparison_support()
    HermesAdapter, SQLiteReference = support.HermesAdapter, support.SQLiteReference
    if len(arm_order) != len(COMPARISON_ARMS) or set(arm_order) != set(COMPARISON_ARMS):
        raise ValueError('Every comparison arm must execute exactly once')
    fixture_path = Path(fixture_path) if fixture_path else Path(__file__).parent / 'lifecycle-20261022' / 'FIXTURE.json'
    fixture_bytes = fixture_path.read_bytes()
    fixture = json.loads(fixture_bytes)
    schedule = comparison_schedule(fixture, variants, seed)
    schedule_bytes = json.dumps(schedule, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    factories = adapter_factories if adapter_factories is not None else {
        'hermes': HermesAdapter,
        'sqlite_retained': lambda root: SQLiteReference(root),
        'sqlite_snapshot_local': lambda root: SQLiteReference(root, snapshot_local=True)}
    arms = {}
    with tempfile.TemporaryDirectory() as directory:
        for arm in arm_order:
            profile = 'snapshot_local' if arm == 'sqlite_snapshot_local' else 'retained_authority'
            cases = []
            for index, case in enumerate(schedule):
                root = Path(directory) / arm / str(index)
                root.mkdir(parents=True)
                try:
                    adapter = factories[arm](root)
                    result = replay_comparison_case(adapter, case, profile)
                except Exception as error:
                    result = {'case_id': case['case_id'], 'scenario': case['scenario'], 'variant': case['variant'],
                              'planned_operations': len(case['operations']), 'observations': [], 'completed': False,
                              'oracle_passed': False, 'profile_passed': False,
                              'initialization_error': {'exception': type(error).__name__, 'message': str(error)}}
                cases.append(result)
            deterministic_bytes = json.dumps(comparison_deterministic_view(cases), sort_keys=True,
                                             ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            arms[arm] = {'profile': profile, 'counts': summarize_comparison(cases), 'cases': cases,
                         'deterministic_observations_sha256': hashlib.sha256(deterministic_bytes).hexdigest()}
    report = {'mode': 'matched_lifecycle_transitions_v1', 'schema_version': 1, 'seed': seed,
              'variants_per_scenario': variants, 'scenarios': len(COMPARISON_SCENARIOS),
              'cases_per_arm': len(schedule), 'fixture_sha256': hashlib.sha256(fixture_bytes).hexdigest(),
              'schedule_sha256': hashlib.sha256(schedule_bytes).hexdigest(),
              'case_order': [case['case_id'] for case in schedule], 'arms': arms,
              'primary_comparison': ['hermes', 'sqlite_retained'],
              'context_ablation': 'sqlite_snapshot_local',
              'provider_requests': 0, 'independent_clients': 0, 'speed_comparison': False,
              'physical_crash_simulation': False, 'winner_prespecified': False,
              'oracle_passed': all(case['oracle_passed'] for arm in ('hermes', 'sqlite_retained') for case in arms[arm]['cases']),
              'profile_conformance_passed': all(case['profile_passed'] for arm in COMPARISON_ARMS for case in arms[arm]['cases'])}
    if emit:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trajectories', type=int, help='Run 1..3000 seeded core transition trajectories.')
    parser.add_argument('--compare-transitions', action='store_true', help='Compare three lifecycle arms against the frozen synthetic oracle.')
    parser.add_argument('--comparison-fixture', type=Path, help='Explicit lifecycle fixture (default: packaged frozen fixture).')
    parser.add_argument('--variants', type=int, help='Lifecycle variants per scenario: 1..10 (default 10).')
    parser.add_argument('--lance-hybrid', action='store_true',
                        help='Run the optional local synthetic LanceDB binding demo.')
    parser.add_argument('--documents', type=int, help='Typed volume mode: 1..5000 synthetic sources (default 24).')
    parser.add_argument('--repetitions', type=int, help='Typed volume mode: 1..100000 retrievals (default 10).')
    parser.add_argument('--seed', type=int, help='Typed volume mode: query seed 0..2^64-1 (default 0).')
    args = parser.parse_args()
    if not args.compare_transitions and (args.comparison_fixture is not None or args.variants is not None):
        parser.error('--comparison-fixture and --variants require --compare-transitions')
    if args.compare_transitions and (args.trajectories is not None or args.lance_hybrid or args.documents is not None or args.repetitions is not None):
        parser.error('--compare-transitions cannot be combined with another mode')
    if args.compare_transitions:
        variants = 10 if args.variants is None else args.variants
        comparison_seed = COMPARISON_SEED if args.seed is None else args.seed
        if not 1 <= variants <= 10 or not 0 <= comparison_seed < 2 ** 64:
            parser.error('Expected variants 1..10 and uint64 seed')
        comparison = compare_transitions(args.comparison_fixture, variants, comparison_seed)
        raise SystemExit(0 if comparison['oracle_passed'] and comparison['profile_conformance_passed'] else 1)
    volume = any(value is not None for value in (args.documents, args.repetitions, args.seed))
    if args.trajectories is not None and (args.lance_hybrid or args.documents is not None or args.repetitions is not None):
        parser.error('--trajectories cannot be combined with retrieval or Lance modes')
    if args.trajectories is not None and not 1 <= args.trajectories <= 3000:
        parser.error('Expected trajectories 1..3000')
    if args.lance_hybrid and volume:
        parser.error('--lance-hybrid cannot be combined with typed volume options')
    documents = 24 if args.documents is None else args.documents
    repetitions = 10 if args.repetitions is None else args.repetitions
    seed = 0 if args.seed is None else args.seed
    if not 1 <= documents <= 5000 or not 1 <= repetitions <= 100000 or not 0 <= seed < 2 ** 64:
        parser.error('Expected documents 1..5000, repetitions 1..100000 and seed 0..2^64-1')
    if args.trajectories is not None:
        transition_trajectories(args.trajectories, seed)
    elif args.lance_hybrid:
        lance_hybrid_demo()
    else:
        report = main(documents, repetitions, seed, volume=volume)
        if volume and not report['oracle_passed']:
            raise SystemExit(1)
