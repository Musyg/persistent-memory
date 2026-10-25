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


def main(documents=24, repetitions=10, seed=0, *, volume=False, progress_path=None, profile_tail=False, incremental_batch=0):
    if not (type(documents) is int and 1 <= documents <= 5000
            and type(repetitions) is int and 1 <= repetitions <= 100000
            and type(seed) is int and 0 <= seed < 2 ** 64):
        raise ValueError('Expected documents 1..5000, repetitions 1..100000 and seed 0..2^64-1')
    if progress_path is not None and not volume:
        raise ValueError('Volume progress requires typed volume mode')
    if profile_tail and (not volume or progress_path is None):
        raise ValueError('Tail profiling requires instrumented typed volume mode')
    if type(incremental_batch) is not int or not 0 <= incremental_batch <= 100:
        raise ValueError('Expected incremental_batch 0 (disabled) or 2..100')
    if incremental_batch:
        import sys
        if (incremental_batch < 2 or not volume or progress_path is None
                or sys.platform != 'linux' or profile_tail
                or documents + incremental_batch > 5000 or repetitions < incremental_batch):
            raise ValueError('Incremental cycle requires Linux instrumented volume mode, batch 2..100, '
                             'total documents <=5000, repetitions >=batch and no tail profile')
    incremental_cycle = None
    profiler = None
    if profile_tail:
        import cProfile
        profiler = cProfile.Profile()
    phase_metrics = {}
    telemetry_started = time.perf_counter()
    telemetry_writes = 0
    def sample(root):
        import os
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        io = None
        proc = Path('/proc/self/io')
        if proc.is_file():
            io = {k: int(v) for k, v in (line.split(':', 1) for line in proc.read_text().splitlines())}
        storage = {p.name: p.stat().st_size for p in root.iterdir() if p.is_file()}
        current_rss = None
        statm = Path('/proc/self/statm')
        if statm.is_file():
            current_rss = int(statm.read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')
        return {'elapsed_seconds': time.perf_counter() - telemetry_started,
                'cpu_user_seconds': usage.ru_utime, 'cpu_system_seconds': usage.ru_stime,
                'io': io, 'storage_bytes': storage, 'storage_total_bytes': sum(storage.values()),
                'rss_current_bytes': current_rss, 'rss_peak_native_units': usage.ru_maxrss}
    def progress(root, phase, completed, total):
        nonlocal telemetry_writes
        if progress_path is None:
            return
        import os
        target = Path(progress_path)
        if target.is_symlink() or target.parent.is_symlink():
            raise ValueError('Volume progress must be a regular path')
        value = {'schema': 'persistent-memory.volume-progress.v1', 'phase': phase,
                 'completed': completed, 'planned': total, 'documents': documents,
                 'repetitions': repetitions, 'seed': seed, 'sample': sample(root)}
        temporary = target.with_name(target.name + '.tmp')
        with temporary.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(value, sort_keys=True) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        telemetry_writes += 1
    def boundary(root, phase, where):
        if progress_path is not None:
            phase_metrics.setdefault(phase, {})[where] = sample(root)
            progress(root, phase + '_' + where, 0 if where == 'start' else 1, 1)
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
        boundary(root, 'ingest', 'start')
        ingest_started = time.perf_counter()
        for index in range(documents):
            if profiler is not None and index == max(0, documents - 10):
                profiler.enable()
            text = 'Synthetic copper item number ' + str(index)
            if volume:
                text += ' token' + format(index, '06d')
            refs.append(typed.put('example', 'note-' + str(index),
                                  text,
                                  {'evidence_kind': 'observation'})['ref'])
            operations['typed.put'] += 1
            if (index + 1) % 50 == 0 or index + 1 == documents:
                progress(root, 'ingest', index + 1, documents)
        if profiler is not None:
            profiler.disable()
        ingest_seconds = time.perf_counter() - ingest_started
        boundary(root, 'ingest', 'end')
        boundary(root, 'initial_sync', 'start')
        sync_started = time.perf_counter()
        typed.sync('example')
        operations['typed.sync'] += 1
        initial_sync_seconds = time.perf_counter() - sync_started
        boundary(root, 'initial_sync', 'end')
        if incremental_batch:
            # This oracle is built from the fixed synthetic sources, never search output.
            expected_metadata = {'evidence_kind': 'observation', 'valid_from': None,
                                 'valid_until': None, 'observed_at': None, 'aliases': [],
                                 'preconditions': {}, 'confidence': None}
            expected_texts = ['Synthetic copper item number ' + str(index) + ' token' + format(index, '06d')
                              for index in range(documents + incremental_batch)]
            def check(condition, reason):
                if not condition:
                    raise AssertionError('incremental_oracle:' + reason)
            def exact_read(index, allowed=True):
                read_started = time.perf_counter()
                decision = memory.read(refs[index])
                read_timings.append(time.perf_counter() - read_started)
                operations['memory.read'] += 1
                check(decision.get('ref') == refs[index], 'read_ref')
                check(decision.get('allowed') is allowed, 'read_allowed')
                if allowed:
                    expected_content = json.dumps({'schema': 'hermes.typed-memory.v1',
                                                   'text': expected_texts[index],
                                                   'metadata': expected_metadata},
                                                  ensure_ascii=False, sort_keys=True,
                                                  separators=(',', ':'), allow_nan=False)
                    check(decision.get('content') == expected_content, 'read_content')
                else:
                    check('content' not in decision, 'revoked_content_exposed')
            def exact_search(result, index):
                check(result.get('status') == 'completed', 'search_status')
                check(result.get('complete') is True, 'search_incomplete')
                check(result.get('coverage', {}).get('candidate_truncated') is False,
                      'search_truncated')
                check(result.get('exclusions') == [], 'search_exclusions')
                items = result.get('items')
                check(type(items) is list and len(items) == 1, 'search_cardinality')
                check(items[0].get('ref') == refs[index], 'search_ref')
                check(items[0].get('text') == expected_texts[index], 'search_content')
                check(items[0].get('metadata') == expected_metadata, 'search_metadata')
                check(result.get('context') == expected_texts[index], 'search_context')
                check(len(result['context']) <= 200, 'search_context_budget')
            timings, read_timings = [], []
            setup_operations = dict(operations)
            cycle_started = time.perf_counter()
            boundary(root, 'incremental_admit', 'start')
            for index in range(documents, documents + incremental_batch):
                reference = typed.put('example', 'note-' + str(index), expected_texts[index],
                                      {'evidence_kind': 'observation'})['ref']
                operations['typed.put'] += 1
                check(set(reference) == {'workspace', 'artifact_id', 'version_id'}
                      and reference['workspace'] == 'example'
                      and reference['artifact_id'] == 'note-' + str(index)
                      and type(reference['version_id']) is str and bool(reference['version_id']),
                      'admission_ref')
                refs.append(dict(reference))
            boundary(root, 'incremental_admit', 'end')
            boundary(root, 'incremental_read', 'start')
            for index in range(documents, documents + incremental_batch):
                exact_read(index)
            boundary(root, 'incremental_read', 'end')
            boundary(root, 'incremental_sync', 'start')
            typed.sync('example')
            operations['typed.sync'] += 1
            boundary(root, 'incremental_sync', 'end')
            boundary(root, 'search_and_read', 'start')
            schedule = list(range(documents, documents + incremental_batch))
            schedule.extend(generator.randrange(documents) for _ in range(repetitions - incremental_batch))
            for position, selected in enumerate(schedule, 1):
                query = 'token' + format(selected, '06d')
                query_digest.update((query + '\n').encode('ascii'))
                queried.add(selected)
                search_started = time.perf_counter()
                result = typed.search('example', query, top_k=5, max_context_chars=200)
                timings.append(time.perf_counter() - search_started)
                operations['typed.search'] += 1
                exact_search(result, selected)
                exact_read(selected)
                hits += 1
                statuses['completed'] = statuses.get('completed', 0) + 1
                if position % 10 == 0 or position == repetitions:
                    progress(root, 'search_and_read', position, repetitions)
            boundary(root, 'search_and_read', 'end')
            boundary(root, 'revoke_and_stale_check', 'start')
            memory.revoke_source('example', 'note-' + str(documents), 'example-incremental-revoke')
            operations['memory.revoke_source'] += 1
            exact_read(documents, allowed=False)
            revocation_query = 'token' + format(documents, '06d')
            stale = typed.search('example', revocation_query, top_k=5, max_context_chars=200)
            operations['typed.search'] += 1
            check(stale.get('status') == 'index_stale' and stale.get('items') == []
                  and stale.get('context') == '', 'revoked_index_not_stale')
            boundary(root, 'revoke_and_stale_check', 'end')
            boundary(root, 'maintenance_sync', 'start')
            resync_started = time.perf_counter()
            typed.sync('example')
            operations['typed.sync'] += 1
            revocation_sync_seconds = time.perf_counter() - resync_started
            boundary(root, 'maintenance_sync', 'end')
            boundary(root, 'after_revoke_check', 'start')
            after = typed.search('example', revocation_query, top_k=5, max_context_chars=200)
            operations['typed.search'] += 1
            check(after.get('status') == 'completed' and after.get('complete') is True
                  and after.get('items') == [] and after.get('context') == ''
                  and after.get('coverage', {}).get('candidate_truncated') is False,
                  'revoked_search_not_empty')
            exact_read(documents, allowed=False)
            witness_index = documents + 1
            witness = typed.search('example', 'token' + format(witness_index, '06d'),
                                   top_k=5, max_context_chars=200)
            operations['typed.search'] += 1
            exact_search(witness, witness_index)
            exact_read(witness_index)
            disk_bytes = sum(path.stat().st_size for path in root.rglob('*') if path.is_file())
            boundary(root, 'after_revoke_check', 'end')
            incremental_cycle = {
                'schema': 'persistent-memory.incremental-cycle.v1',
                'batch': incremental_batch, 'initial_documents': documents,
                'admitted_documents': documents + incremental_batch,
                'active_documents_after_revocation': documents + incremental_batch - 1,
                'new_retrieval_trials': incremental_batch,
                'initial_retrieval_trials': repetitions - incremental_batch,
                'explicit_admission_reads': incremental_batch,
                'query_schedule_sha256': query_digest.hexdigest(),
                'query_order': 'each new source in admission order, then seeded initial-source draws',
                'setup_phases': ['ingest', 'initial_sync'],
                'marginal_phases': ['incremental_admit', 'incremental_read', 'incremental_sync',
                                    'search_and_read', 'revoke_and_stale_check',
                                    'maintenance_sync', 'after_revoke_check'],
                'marginal_elapsed_seconds': time.perf_counter() - cycle_started,
                'marginal_public_method_calls': {key: operations[key] - setup_operations[key]
                                               for key in operations},
                'oracle_passed': True, 'revoked_reads_refused': 2,
                'revoked_source': 'note-' + str(documents),
                'valid_control_source': 'note-' + str(witness_index),
                'same_memory_instance': True, 'setup_excluded_from_marginal': True,
                'telemetry_cost_included': True, 'telemetry_overhead_seconds': None,
                'infrastructure_price_usd': None, 'energy_joules': None}
        else:
            boundary(root, 'search_and_read', 'start')
            timings = []
            read_timings = []
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
                    read_started = time.perf_counter()
                    assert memory.read(item['ref'])['allowed']
                    read_timings.append(time.perf_counter() - read_started)
                    operations['memory.read'] += 1
                if (_ + 1) % 10 == 0 or _ + 1 == repetitions:
                    progress(root, 'search_and_read', _ + 1, repetitions)
            boundary(root, 'search_and_read', 'end')
            boundary(root, 'revoke_and_stale_check', 'start')
            memory.revoke_source('example', 'note-0', 'example-revoke-0')
            operations['memory.revoke_source'] += 1
            revocation_query = 'token000000' if volume else 'copper'
            stale = typed.search('example', revocation_query)
            operations['typed.search'] += 1
            assert stale['status'] != 'completed'
            boundary(root, 'revoke_and_stale_check', 'end')
            boundary(root, 'maintenance_sync', 'start')
            resync_started = time.perf_counter()
            typed.sync('example')
            operations['typed.sync'] += 1
            revocation_sync_seconds = time.perf_counter() - resync_started
            boundary(root, 'maintenance_sync', 'end')
            boundary(root, 'after_revoke_check', 'start')
            after = typed.search('example', revocation_query)
            operations['typed.search'] += 1
            assert all(item['ref'] != refs[0] for item in after['items'])
            if volume:
                assert stale['status'] == 'index_stale'
                assert after['status'] == 'completed' and after['items'] == []
                disk_bytes = sum(path.stat().st_size for path in root.rglob('*') if path.is_file())
            boundary(root, 'after_revoke_check', 'end')
        progress(root, 'completed', repetitions, repetitions)
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
        if incremental_cycle is not None:
            report['mode'] = 'synthetic_typed_volume_incremental'
            report['incremental_cycle'] = incremental_cycle
        if progress_path is not None:
            report['end_to_end_telemetry'] = {
                'schema': 'persistent-memory.volume-costs.v1',
                'phases': phase_metrics, 'progress_writes': telemetry_writes,
                'elapsed_seconds': time.perf_counter() - telemetry_started,
                'explicit_read_seconds': sum(read_timings),
                'explicit_read_trials': len(read_timings),
                'scope': 'same process; includes revalidation and telemetry; no cold-cache control',
                'provider_requests': 0, 'infrastructure_price_usd': None,
                'energy_joules': None, 'efficiency_superiority_demonstrated': False}
            if profiler is not None:
                import pstats
                profile = pstats.Stats(profiler)
                report['tail_profile'] = {
                    'scope': 'last ten source admissions only; these timings are profiled',
                    'admissions_profiled': min(10, documents),
                    'top_cumulative': [
                        {'file': Path(key[0]).name, 'line': key[1], 'function': key[2],
                         'primitive_calls': value[0], 'calls': value[1],
                         'own_seconds': value[2], 'cumulative_seconds': value[3]}
                        for key, value in sorted(profile.stats.items(), key=lambda pair: pair[1][3], reverse=True)[:40]]}
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


ACTION_SUPPORT_SHA256 = '7398732d97beaf9d511a9792f29b5265102c235c08f64ed34e60772f08e96914'


def _action_support():
    import importlib.util
    import sys
    path = Path(__file__).resolve().with_name('action_transfer.py')
    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != ACTION_SUPPORT_SHA256:
        raise ValueError('action_support_source_pin')
    key = '_persistent_memory_action_support_' + ACTION_SUPPORT_SHA256[:16]
    existing = sys.modules.get(key)
    if existing is not None:
        if Path(existing.__file__).resolve() != path:
            raise ValueError('action_support_module_conflict')
        return existing
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[key]
        raise
    return module


def _action_json_file(path, pin):
    support = _action_support()
    support.require(path is not None and pin is not None, 'explicit_pinned_action_input_required')
    raw = support._file_bytes(path, maximum=4 * 1024 ** 2)
    support.require(hashlib.sha256(raw).hexdigest() == support._pin(pin), 'action_input_pin_mismatch')
    return support.json_value(raw)


def _action_dump(path, value):
    support = _action_support()
    raw = (support.canonical(value) + '\n').encode('utf-8')
    support._write_new(path, raw)
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}


def _action_provider_arguments(args, cell):
    support = _action_support()
    paid = (args.action_grant, args.action_grant_sha256, args.action_provider_source,
            args.action_credential_reader_source)
    if args.action_provider_mode == 'fake':
        support.require(all(value is None for value in paid), 'fake_mode_forbids_paid_paths')
        fake = _action_json_file(args.action_fake_response, args.action_fake_response_sha256)
        support.require(type(fake) is dict and set(fake) == {'schema', 'cell_id', 'body', 'finish_reason'}
                        and fake['schema'] == 'persistent-memory.action-transfer.fake-response.v1'
                        and fake['cell_id'] == cell['cell_id'] and type(fake['body']) is str
                        and fake['finish_reason'] in ('stop', 'length'), 'literal_fake_response_binding')
        return {'mode': 'fake', 'fake_response': fake['body'], 'fake_finish_reason': fake['finish_reason']}
    support.require(all(value is not None for value in paid) and args.action_fake_response is None
                    and args.action_fake_response_sha256 is None, 'explicit_paid_grant_and_sources_required')
    return {'mode': 'paid', 'grant_path': args.action_grant, 'grant_sha256': args.action_grant_sha256,
            'provider_path': args.action_provider_source, 'credential_reader_path': args.action_credential_reader_source}


def action_transfer_phase(args):
    """One child phase over a pinned projection; never opens a fixture or full plan."""
    support = _action_support()
    support.require(args.action_fixture is None and args.action_fixture_sha256 is None
                    and args.action_plan is None and args.action_plan_sha256 is None and args.action_cell_id is None,
                    'child_phase_must_not_receive_fixture_or_full_plan')
    projection = _action_json_file(args.action_input, args.action_input_sha256)
    support.require(args.action_output is not None, 'action_phase_receipt_required')
    xp_only = (args.action_extraction, args.action_extraction_sha256,
               args.action_extraction_exit, args.action_extraction_exit_sha256,
               args.action_verification, args.action_verification_sha256,
               args.action_feedback, args.action_feedback_sha256, args.action_ledger)
    if projection.get('schema') != 'persistent-memory.experience.phase.v1':
        support.require(all(value is None for value in xp_only), 'legacy_phase_forbids_experience_inputs')
    if args.action_phase != 'extract':
        support.require(all(value is None for value in (args.action_verification, args.action_verification_sha256,
                        args.action_feedback, args.action_feedback_sha256, args.action_ledger)), 'feedback_inputs_require_extract')
    if args.action_phase != 'observe':
        support.require(all(value is None for value in (args.action_extraction, args.action_extraction_sha256,
                        args.action_extraction_exit, args.action_extraction_exit_sha256)), 'extraction_inputs_require_observe')
    if args.action_phase == 'observe':
        support.require(args.action_state is not None and args.action_artifacts is None
                        and args.action_prior_receipt is None and args.action_prior_receipt_sha256 is None
                        and args.action_prior_exit is None and args.action_prior_exit_sha256 is None
                        and args.action_fake_response is None and args.action_fake_response_sha256 is None
                        and args.action_grant is None and args.action_grant_sha256 is None
                        and args.action_provider_source is None and args.action_credential_reader_source is None
                        and args.action_provider_mode == 'fake', 'observe_phase_arguments')
        if projection.get('schema') == 'persistent-memory.experience.phase.v1':
            extraction = None
            if args.action_extraction is not None or args.action_extraction_sha256 is not None:
                extraction = _action_json_file(args.action_extraction, args.action_extraction_sha256)
                extraction_exit = _action_json_file(args.action_extraction_exit, args.action_extraction_exit_sha256)
            else:
                support.require(args.action_extraction_exit is None and args.action_extraction_exit_sha256 is None,
                                'extraction_exit_requires_receipt')
                extraction_exit = None
            receipt = support.observe_experience(projection, args.action_state, extraction=extraction,
                                                extraction_exit=extraction_exit)
        else:
            support.require(args.action_extraction is None and args.action_extraction_sha256 is None,
                            'legacy_observe_forbids_experience')
            receipt = support.observe(projection, args.action_state)
    else:
        prior = _action_json_file(args.action_prior_receipt, args.action_prior_receipt_sha256)
        observed_exit = _action_json_file(args.action_prior_exit, args.action_prior_exit_sha256)
        support.require(args.action_phase == 'extract' or args.action_artifacts is not None,
                        'artifact_directory_required')
        if args.action_phase == 'extract':
            support.require(projection.get('schema') == 'persistent-memory.experience.phase.v1'
                            and args.action_state is None and args.action_artifacts is None,
                            'extraction_requires_experience_projection')
            verification = _action_json_file(args.action_verification, args.action_verification_sha256)
            feedback = _action_json_file(args.action_feedback, args.action_feedback_sha256)
            receipt = support.extract_procedure(projection, prior, verification, observed_exit, feedback,
                        ledger_path=args.action_ledger,
                        **_action_provider_arguments(args, projection['cell']))
        elif args.action_phase == 'propose':
            support.require(args.action_state is not None, 'p2_state_required')
            receipt = support.propose_and_consume(projection, args.action_state, args.action_artifacts,
                        prior, observed_exit, **_action_provider_arguments(args, projection['cell']))
        else:
            support.require(args.action_state is None and args.action_fake_response is None
                            and args.action_fake_response_sha256 is None and args.action_grant is None
                            and args.action_grant_sha256 is None and args.action_provider_source is None
                            and args.action_credential_reader_source is None and args.action_provider_mode == 'fake',
                            'verifier_must_not_receive_provider_or_state')
            receipt = support.verify_actual_files(projection, args.action_artifacts, prior, observed_exit)
    _action_dump(args.action_output, receipt)
    print(support.canonical(receipt))
    return receipt


def action_transfer_cell(args):
    """Existing benchmark parent: select one frozen cell, then reap P1, P2 and P3."""
    import os
    import subprocess
    import sys
    support = _action_support()
    support.require(sys.platform == 'linux', 'action_process_execution_requires_linux')
    support.require(args.action_input is None and args.action_input_sha256 is None and args.action_state is None
                    and args.action_artifacts is None and args.action_prior_receipt is None
                    and args.action_prior_receipt_sha256 is None and args.action_prior_exit is None
                    and args.action_prior_exit_sha256 is None, 'parent_phase_inputs_are_derived')
    support.require(all(getattr(args, 'action_' + suffix) is None for suffix in (
                    'extraction', 'extraction_sha256', 'extraction_exit', 'extraction_exit_sha256',
                    'verification', 'verification_sha256', 'feedback', 'feedback_sha256', 'ledger')),
                    'legacy_parent_forbids_experience_inputs')
    fixture = _action_json_file(args.action_fixture, args.action_fixture_sha256)
    plan = _action_json_file(args.action_plan, args.action_plan_sha256)
    support.require(type(fixture) is dict and set(fixture) == {'schema', 'synthetic', 'templates', 'worlds'}
                    and fixture['schema'] == 'persistent-memory.action-transfer.fixture.v1'
                    and fixture['synthetic'] is True and len(fixture['worlds']) == 24
                    and len(fixture['templates']) == 12, 'action_fixture_scope')
    worlds = {world['world_id']: world for world in fixture['worlds']}
    templates = {template['template_id']: template for template in fixture['templates']}
    support.require(len(worlds) == 24 and len(templates) == 12
                    and {world['template_id'] for world in worlds.values()} == set(templates), 'action_world_template_identity')
    support.require(type(plan) is dict and set(plan) == {'schema', 'dataset_sha256', 'cells'}
                    and plan['schema'] == 'persistent-memory.action-transfer.plan.v1'
                    and plan['dataset_sha256'] == args.action_fixture_sha256
                    and type(plan['cells']) is list and len(plan['cells']) == 576, 'action_plan_scope')
    selected, seen_ids, actual = None, set(), set()
    for candidate in plan['cells']:
        cell = support._cell(candidate)
        support.require(cell['cell_id'] not in seen_ids and cell['world_id'] in worlds
                        and cell['template_id'] == worlds[cell['world_id']]['template_id'], 'plan_cell_world_binding')
        seen_ids.add(cell['cell_id'])
        actual.add((cell['world_id'], cell['model'], cell['arm'], cell['repetition']))
        if cell['cell_id'] == args.action_cell_id:
            selected = cell
    expected = {(world, model, arm, rep) for world in worlds for model in support.MODELS
                for arm in support.ARMS for rep in (1, 2, 3)}
    support.require(actual == expected and len(seen_ids) == len(actual) == 576 and selected is not None,
                    'complete_immutable_cell_plan_required')
    support.require(args.action_output is not None, 'new_action_output_directory_required')
    # Validate the literal fake response or presence of paid arguments before spawning.
    _action_provider_arguments(args, selected)
    root = Path(args.action_output)
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    root = root.resolve()
    state, artifacts = root / 'state', root / 'artifacts'
    phases, exits = {}, {}
    prior_ref = prior_exit_ref = None
    world = worlds[selected['world_id']]
    for phase in ('observe', 'propose', 'verify'):
        folder = root / phase
        folder.mkdir(mode=0o700)
        # In particular, the oracle projection does not exist until P2 has exited.
        projection = support.project_world(world, selected, phase,
            dataset_sha256=args.action_fixture_sha256, plan_sha256=args.action_plan_sha256)
        projected = _action_dump(folder / 'INPUT.json', projection)
        receipt_path = root / (phase + '-receipt.json')
        command = [sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--action-transfer', '--action-phase', phase,
                   '--action-input', projected['path'], '--action-input-sha256', projected['sha256'],
                   '--action-output', str(receipt_path)]
        if phase in ('observe', 'propose'):
            command += ['--action-state', str(state.resolve())]
        if phase != 'observe':
            command += ['--action-artifacts', str(artifacts.resolve()),
                        '--action-prior-receipt', prior_ref['path'], '--action-prior-receipt-sha256', prior_ref['sha256'],
                        '--action-prior-exit', prior_exit_ref['path'], '--action-prior-exit-sha256', prior_exit_ref['sha256']]
        if phase == 'propose':
            command += ['--action-mode', args.action_provider_mode]
            provider_fields = (('action_fake_response', '--action-fake-response'),
                ('action_fake_response_sha256', '--action-fake-response-sha256'), ('action_grant', '--action-grant'),
                ('action_grant_sha256', '--action-grant-sha256'), ('action_provider_source', '--action-provider-source'),
                ('action_credential_reader_source', '--action-credential-reader-source'))
            for attr, flag in provider_fields:
                item = getattr(args, attr)
                if item is not None:
                    command += [flag, str(item.resolve()) if isinstance(item, Path) else item]
        process = subprocess.Popen(command, cwd=folder, env={'PATH': os.defpath, 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'},
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=240)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            stdout, stderr = process.communicate()
        observed_exit = {'pid': process.pid, 'returncode': process.returncode, 'exited_ns': time.monotonic_ns()}
        support._write_new(folder / 'STDOUT.txt', stdout.encode('utf-8'))
        support._write_new(folder / 'STDERR.txt', stderr.encode('utf-8'))
        exit_ref = _action_dump(folder / 'EXIT.json', observed_exit)
        support.require(not timed_out and process.returncode == 0 and receipt_path.is_file(), 'action_child_failed:' + phase)
        raw = support._file_bytes(receipt_path, maximum=4 * 1024 ** 2)
        receipt = support.json_value(raw)
        support.require(stdout.encode('utf-8') == raw and receipt['pid'] == process.pid
                        and receipt['cell'] == selected and receipt['dataset_sha256'] == args.action_fixture_sha256
                        and receipt['plan_sha256'] == args.action_plan_sha256
                        and receipt['ended_ns'] <= observed_exit['exited_ns'], 'action_child_receipt_binding')
        phases[phase] = {'receipt': receipt, 'receipt_sha256': hashlib.sha256(raw).hexdigest(),
                         'projection_sha256': projected['sha256']}
        exits[phase] = observed_exit
        prior_ref = {'path': str(receipt_path.resolve()), 'sha256': phases[phase]['receipt_sha256']}
        prior_exit_ref = {'path': str(Path(exit_ref['path']).resolve()), 'sha256': exit_ref['sha256']}
    report = {'schema': 'persistent-memory.action-transfer.cell-report.v1', 'cell': selected,
              'dataset_sha256': args.action_fixture_sha256, 'plan_sha256': args.action_plan_sha256,
              'fake_proof_only': args.action_provider_mode == 'fake', 'phases': phases, 'exits': exits,
              'task_success': phases['verify']['receipt']['task_success'],
              'provider_called': phases['propose']['receipt']['provider_called'],
              'runtime_activated': False, 'autonomous_learning_claimed': False}
    _action_dump(root / 'REPORT.json', report)
    print(support.canonical(report))
    return report


EFFICIENCY_INPUTS_SHA256 = '76a58fae321ccbb99ef0376ca6e4249aa15203689d4589a0d3f9a07cbd2b13e7'
EFFICIENCY_GROUPS = (('gpt-6-luna', 'memory_off'), ('gpt-6-luna', 'memory_on'),
                     ('gpt-6-luna', 'simple_baseline'), ('gpt-6.1-sol', 'memory_off'),
                     ('gpt-6.1-sol', 'memory_on'))


def _efficiency_require(condition, reason):
    if not condition:
        raise ValueError('efficiency:' + reason)


def _efficiency_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _efficiency_require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('efficiency:nonfinite_json:' + value)
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


def calculate_efficiency(generations, frozen_report, historical_prices):
    """Pure post-hoc join of observed usage and already-frozen quality; no scorer."""
    from collections import Counter, defaultdict
    from decimal import Decimal, InvalidOperation
    import copy
    import re

    check = _efficiency_require
    check(type(generations) is dict and type(frozen_report) is dict, 'input_objects')
    check(type(historical_prices) is dict and set(historical_prices) == {
        'observed_utc', 'USD_per_million', 'source_urls', 'source_sha256', 'pricing_mode'}, 'price_schema')
    check(type(historical_prices['observed_utc']) is str and historical_prices['observed_utc']
          and type(historical_prices['pricing_mode']) is str and historical_prices['pricing_mode']
          and type(historical_prices['source_sha256']) is str
          and re.fullmatch('[0-9a-f]{64}', historical_prices['source_sha256']) is not None
          and type(historical_prices['source_urls']) is list and len(historical_prices['source_urls']) == 2
          and all(type(url) is str and url.startswith('https://developers.openai.com/')
                  for url in historical_prices['source_urls']), 'price_provenance')
    rates = historical_prices['USD_per_million']
    expected_rates = {'gpt-6-luna': ('0.10', '0.50'), 'gpt-6.1-sol': ('2.00', '10.00')}
    check(type(rates) is dict and set(rates) == set(expected_rates), 'price_models')
    prices = {}
    for model, expected in expected_rates.items():
        check(type(rates[model]) is dict and set(rates[model]) == {'input', 'output'}, 'price_fields')
        parsed = []
        for field, fixed in zip(('input', 'output'), expected):
            value = rates[model][field]
            check(type(value) is str and 0 < len(value) <= 32, 'price_string')
            try:
                number = Decimal(value)
            except InvalidOperation as error:
                raise ValueError('efficiency:invalid_price') from error
            check(number.is_finite() and number > 0 and number == Decimal(fixed), 'historical_price_changed')
            parsed.append(number)
        prices[model] = parsed
    check(generations.get('schema') == 'persistent-memory.volume.normalized-generations.v1'
          and generations.get('development_only') is False and generations.get('oracle_opened') is False
          and type(generations.get('planned_episodes')) is int and generations['planned_episodes'] == 1500
          and type(generations.get('emission_unknown_episodes')) is int
          and generations['emission_unknown_episodes'] == 0, 'generation_scope')
    check(frozen_report.get('schema') == 'persistent-memory.volume.analysis.v1'
          and frozen_report.get('planned_episodes') == 1500 and frozen_report.get('planned_tasks') == 100
          and frozen_report.get('execution_confirmed_complete') is True, 'quality_scope')
    tasks = frozen_report.get('primary', {}).get('tasks')
    check(type(tasks) is list and len(tasks) == 100, 'task_denominator')
    task_map, scenario_groups, families = {}, set(), Counter()
    for task in tasks:
        check(type(task) is dict, 'task_shape')
        case, group, family = (task.get(field) for field in ('case_id', 'scenario_group', 'family'))
        check(type(case) is str and re.fullmatch('V22-F(0[1-9]|10)-G(0[1-9]|10)-T01', case)
              and group == case[:-4] and family == case[4:7]
              and case not in task_map and group not in scenario_groups, 'task_binding')
        task_map[case] = task
        scenario_groups.add(group)
        families[family] += 1
    check(len(scenario_groups) == 100 and len(families) == 10 and set(families.values()) == {10},
          'scenario_group_denominator')
    raw = generations.get('results')
    episodes = frozen_report.get('episodes')
    check(type(raw) is dict and len(raw) == 1500 and type(episodes) is list and len(episodes) == 1500,
          'episode_denominator')
    quality = {}
    for episode in episodes:
        check(type(episode) is dict and type(episode.get('cell_id')) is str
              and episode['cell_id'] not in quality, 'duplicate_or_invalid_quality_cell')
        quality[episode['cell_id']] = episode
    check(set(raw) == set(quality), 'generation_quality_cell_set')
    joined, grouped, matched = [], defaultdict(list), {}
    policies = {'memory_off': ('no_memory', 'OFF'), 'memory_on': ('typed_fts_budgeted', 'ON'),
                'simple_baseline': ('core_lexical_budgeted', 'LEX')}
    token_fields = ('prompt_tokens', 'completion_tokens', 'total_tokens')
    for cell_id in sorted(raw):
        row, q = raw[cell_id], quality[cell_id]
        check(type(row) is dict, 'generation_shape')
        model, arm, case, rep = (q.get(k) for k in ('model', 'arm', 'case_id', 'repetition'))
        check((model, arm) in EFFICIENCY_GROUPS and case in task_map
              and type(rep) is int and 1 <= rep <= 3, 'quality_cell_binding')
        policy, suffix = policies[arm]
        prefix = 'L' if model == 'gpt-6-luna' else 'S'
        expected_id = 'V22-' + prefix + '-' + case + '-R' + str(rep) + '-' + suffix
        check(cell_id == expected_id and row.get('cell_id') == cell_id and row.get('case_id') == case
              and type(row.get('repetition')) is int and row['repetition'] == rep - 1
              and row.get('policy_id') == policy and row.get('requested_model') == model
              and row.get('response_model') == model, 'generation_cell_binding')
        check(row.get('status') == q.get('generation_status') == 'completed'
              and row.get('provider_called') is True and row.get('finish_reason') == 'stop'
              and type(row.get('body')) is str and bool(row['body'].strip())
              and row.get('generation_body_sha256') == hashlib.sha256(row['body'].encode('utf-8')).hexdigest()
              and q.get('status') == 'confirmed' and type(q.get('success')) is bool
              and type(q.get('critical_violation')) is bool, 'incomplete_or_unknown_observation')
        check(type(row.get('context')) is str and type(row.get('evidence')) is list
              and (arm != 'memory_off' or (not row['context'] and not row['evidence'])), 'context_scope')
        check(type(row.get('total_ns')) is int and row['total_ns'] >= 0, 'missing_consumer_latency')
        usage = row.get('usage')
        check(type(usage) is dict and all(type(usage.get(k)) is int and 0 <= usage[k] <= 1000000
                                        for k in token_fields), 'incomplete_integer_usage')
        check(usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens']
              and type(row.get('output_tokens')) is int and row['output_tokens'] == usage['completion_tokens'],
              'token_total_mismatch')
        prompt_details, completion_details = usage.get('prompt_tokens_details'), usage.get('completion_tokens_details')
        check(type(prompt_details) is dict and set(prompt_details) == {'audio_tokens', 'cache_write_tokens', 'cached_tokens'}
              and type(completion_details) is dict and set(completion_details) == {
                  'accepted_prediction_tokens', 'audio_tokens', 'reasoning_tokens', 'rejected_prediction_tokens'}
              and all(type(v) is int and v >= 0 for details in (prompt_details, completion_details)
                      for v in details.values()), 'incomplete_usage_details')
        check(prompt_details['cached_tokens'] + prompt_details['cache_write_tokens'] <= usage['prompt_tokens']
              and completion_details['reasoning_tokens'] <= usage['completion_tokens'], 'usage_detail_overflow')
        check(all(value == 0 for value in prompt_details.values())
              and all(completion_details[key] == 0 for key in (
                  'accepted_prediction_tokens', 'audio_tokens', 'rejected_prediction_tokens')),
              'unsupported_cache_audio_or_prediction_tariff')
        cost = (Decimal(usage['prompt_tokens']) * prices[model][0]
                + Decimal(usage['completion_tokens']) * prices[model][1]) / Decimal(1000000)
        item = {'cell_id': cell_id, 'model': model, 'arm': arm, 'case_id': case,
                'scenario_group': task_map[case]['scenario_group'], 'family': task_map[case]['family'],
                'repetition': rep, 'success': q['success'], 'critical_violation': q['critical_violation'],
                'conforming': q['success'] and not q['critical_violation'],
                **{k: usage[k] for k in token_fields},
                'cached_tokens': prompt_details['cached_tokens'], 'cache_write_tokens': prompt_details['cache_write_tokens'],
                'reasoning_tokens': completion_details['reasoning_tokens'],
                'context_chars': len(row['context']), 'context_utf8_bytes': len(row['context'].encode('utf-8')),
                'consumer_total_ns': row['total_ns'],
                'estimated_generation_usd': str(cost)}
        match_key = (model, arm, case, rep)
        check(match_key not in matched, 'duplicate_matched_cell')
        matched[match_key] = item
        grouped[(model, arm)].append(item)
        joined.append(item)
    check(set(grouped) == set(EFFICIENCY_GROUPS), 'model_arm_set')
    summaries, frozen_groups, frozen_latencies = [], {}, {}
    for row in frozen_report.get('by_model_arm', []):
        key = (row.get('model'), row.get('arm'))
        check(key not in frozen_groups, 'duplicate_quality_group')
        frozen_groups[key] = row
    for row in frozen_report.get('latencies_and_usage', []):
        key = (row.get('model'), row.get('arm'))
        check(key not in frozen_latencies, 'duplicate_latency_group')
        frozen_latencies[key] = row
    check(set(frozen_groups) == set(frozen_latencies) == set(EFFICIENCY_GROUPS), 'frozen_group_set')
    metrics = (*token_fields, 'cached_tokens', 'cache_write_tokens', 'reasoning_tokens',
               'context_chars', 'context_utf8_bytes', 'consumer_total_ns')
    for key in EFFICIENCY_GROUPS:
        rows, known, latency = grouped[key], frozen_groups[key], frozen_latencies[key]
        check(len(rows) == 300 and {(r['case_id'], r['repetition']) for r in rows}
              == {(case, rep) for case in task_map for rep in (1, 2, 3)}, 'matched_three_repetitions')
        totals = {field: sum(row[field] for row in rows) for field in metrics}
        positives = sum(row['success'] for row in rows)
        conforming = sum(row['conforming'] for row in rows)
        check(known.get('planned') == known.get('delivered') == 300 and known.get('success') == positives
              and known.get('failure') == 300 - positives and known.get('unknown') == known.get('not_executed') == 0,
              'frozen_quality_aggregate_mismatch')
        check(latency.get('planned') == latency.get('usage_requests') == 300
              and latency.get('usage_missing_requests') == 0
              and latency.get('observed_tokens') == {field: totals[field] for field in token_fields[:2]},
              'frozen_usage_aggregate_mismatch')
        for field in ('observed_all_statuses', 'completed_only'):
            observed = latency.get(field, {})
            check(observed.get('n') == 300 and all(type(observed.get(k)) in (int, float)
                  and math.isfinite(observed[k]) and observed[k] >= 0 for k in ('p50_seconds', 'p95_seconds')),
                  'frozen_latency_coverage')
        cost = sum((Decimal(row['estimated_generation_usd']) for row in rows), Decimal(0))
        summaries.append({'model': key[0], 'arm': key[1], 'answers': 300, 'tasks': 100,
                          'scenario_groups': 100, 'repetitions': 3, 'usage_coverage': 300,
                          'successes': positives, 'conforming_answers': conforming, 'observed': totals,
                          'estimated_generation_usd': str(cost), 'estimated_usd_per_answer': str(cost / 300),
                          'estimated_usd_per_conforming_answer': str(cost / conforming) if conforming else None,
                          'frozen_consumer_latency': copy.deepcopy(latency)})
    contrasts = [('gpt-6-luna', 'memory_on', 'memory_off'),
                 ('gpt-6-luna', 'memory_on', 'simple_baseline'),
                 ('gpt-6.1-sol', 'memory_on', 'memory_off')]
    secondaries = {(row['model'], row['arm_a'], row['arm_b']): row['statistics']
                   for row in frozen_report.get('secondary_comparisons', [])}
    check(set(secondaries) == set(contrasts[1:]) and len(frozen_report['secondary_comparisons']) == 2,
          'frozen_quality_contrasts')
    comparisons = []
    for model, arm_a, arm_b in contrasts:
        pairs = [(matched[(model, arm_a, case, rep)], matched[(model, arm_b, case, rep)])
                 for case in sorted(task_map) for rep in (1, 2, 3)]
        delta = {}
        for field in (*metrics, 'estimated_generation_usd'):
            a_sum = sum((Decimal(str(a[field])) for a, _ in pairs), Decimal(0))
            b_sum = sum((Decimal(str(b[field])) for _, b in pairs), Decimal(0))
            difference = a_sum - b_sum
            delta[field] = {'sum_difference': str(difference) if field == 'estimated_generation_usd' else int(difference),
                            'mean_difference': str(difference / 300),
                            'relative_change_vs_b': float(difference / b_sum) if b_sum else None}
        statistics = frozen_report['primary'] if arm_b == 'memory_off' and model == 'gpt-6-luna' else secondaries[(model, arm_a, arm_b)]
        check(type(statistics.get('effect_uncertainty_interval_95')) is list
              and len(statistics['effect_uncertainty_interval_95']) == 2
              and all(type(value) in (int, float) and math.isfinite(value) and -1 <= value <= 1
                      for value in statistics['effect_uncertainty_interval_95'])
              and statistics['effect_uncertainty_interval_95'][0] <= statistics['effect_uncertainty_interval_95'][1]
              and statistics.get('planned_tasks') == statistics.get('scenario_groups') == 100,
              'frozen_quality_interval')
        outcomes = Counter(('success' if a['success'] else 'failure') + '/' + ('success' if b['success'] else 'failure')
                           for a, b in pairs)
        comparisons.append({'model': model, 'arm_a': arm_a, 'arm_b': arm_b, 'paired_responses': 300,
                            'independent_scenario_groups': 100, 'repetitions_kept_within_case': 3,
                            'observed_deltas_a_minus_b': delta, 'paired_quality_outcomes': dict(outcomes),
                            'frozen_quality_statistics': copy.deepcopy({k: v for k, v in statistics.items() if k != 'tasks'}),
                            'exploratory': True, 'new_uncertainty_estimated': False})
    return {'schema': 'persistent-memory.efficiency-analysis.v1', 'mode': 'frozen_paired_efficiency_v1',
            'post_hoc': True, 'exploratory': True, 'provider_requests': 0, 'new_judgments': 0,
            'tasks': 100, 'scenario_groups': 100, 'repetitions': 3, 'generation_answers': 1500,
            'usage_coverage': 1500, 'usage_missing': 0, 'episodes': joined, 'groups': summaries,
            'paired_comparisons': comparisons, 'historical_prices': copy.deepcopy(historical_prices),
            'estimated_generation_usd': str(sum((Decimal(r['estimated_generation_usd']) for r in joined), Decimal(0))),
            'actual_billed_usd': None, 'cost_scope': 'Generation usage only, at frozen historical standard prices; no invoice, judge, retrieval, storage or operating cost.',
            'reasoning_accounting': 'Reasoning is a subset of completion_tokens and is not charged twice.',
            'cache_policy': 'Observed zero cached/cache-write tokens; nonzero cache, audio or prediction usage is unsupported and rejected.',
            'latency_scope': 'Frozen consumer total_ns summaries include preparation, retrieval, generation and checks; not provider-only latency.',
            'limits': {'quality_noninferiority_confirmed': False, 'equal_budget_comparison': False,
                       'dominance_claimed': False, 'cross_model_causality_claimed': False,
                       'token_uncertainty_estimated': False, 'full_history_baseline': False,
                       'zero_denominator_ratio': 'null', 'context_tokens_separately_measured': False}}


def efficiency_analysis(inputs_path=None, inputs_sha256=None, *, emit=True):
    """Read pinned public receipts and emit a separate, explicitly post-hoc analysis."""
    check = _efficiency_require
    default = Path(__file__).resolve().parent / 'efficiency-20261023' / 'INPUTS.json'
    path = default if inputs_path is None else Path(inputs_path)
    check(inputs_path is None or inputs_sha256 is not None, 'custom_manifest_requires_sha256')
    pin = EFFICIENCY_INPUTS_SHA256 if inputs_sha256 is None else inputs_sha256
    check(type(pin) is str and len(pin) == 64 and all(c in '0123456789abcdef' for c in pin), 'manifest_pin_shape')
    check(path.is_file() and not path.is_symlink() and path.stat().st_size <= 1024 * 1024, 'manifest_file')
    raw = path.read_bytes()
    check(hashlib.sha256(raw).hexdigest() == pin, 'manifest_pin_mismatch')
    config = _efficiency_json(raw)
    check(type(config) is dict and set(config) == {'schema', 'post_hoc', 'inputs', 'historical_prices', 'denominators'}
          and config['schema'] == 'persistent-memory.efficiency-inputs.v1' and config['post_hoc'] is True
          and config['denominators'] == {'tasks': 100, 'scenario_groups': 100, 'repetitions': 3, 'episodes': 1500}
          and type(config['inputs']) is dict and set(config['inputs']) == {'generations', 'report'}, 'manifest_scope')
    root, values = path.resolve().parent.parent, {}
    for name, ref in config['inputs'].items():
        check(type(ref) is dict and set(ref) == {'path', 'sha256'} and type(ref['path']) is str
              and type(ref['sha256']) is str and len(ref['sha256']) == 64, 'input_reference')
        relative = Path(ref['path'])
        target = path.resolve().parent / relative
        check(not relative.is_absolute() and target.is_file() and not target.is_symlink()
              and target.resolve().is_relative_to(root) and target.stat().st_size <= 64 * 1024 ** 2, 'input_path')
        body = target.read_bytes()
        check(hashlib.sha256(body).hexdigest() == ref['sha256'], 'input_pin_mismatch')
        values[name] = _efficiency_json(body)
    check(values['report'].get('provenance', {}).get('inputs', {}).get('generations', {}).get('sha256')
          == config['inputs']['generations']['sha256'], 'quality_generation_pin_binding')
    result = calculate_efficiency(values['generations'], values['report'], config['historical_prices'])
    result['provenance'] = {'inputs_manifest_sha256': pin, 'inputs': config['inputs'],
                            'source_quality_preserved': True, 'source_generations_preserved': True}
    if emit:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    return result


def calculate_experience(observations, plan):
    """Describe the fixed XP plan; never infer missing effects or significance.

    plan is the exact JSON bytes/string, observations is the worker's
    persistent-memory.experience-observations.v1 object. No fixture is read.
    Fake subsets keep all planned denominators and are labelled proof only.
    """
    from decimal import Decimal, localcontext

    def check(ok, reason):
        if not ok:
            raise ValueError(reason)

    def pin(value):
        return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)

    def integer(value):
        return type(value) is int and value >= 0

    def finite(value):
        return type(value) in (int, float) and math.isfinite(value) and value >= 0

    def count(values):
        return {'planned': len(values), 'success': sum(v is True for v in values),
                'failure': sum(v is False for v in values), 'unknown': sum(v is None for v in values)}

    def duration(receipt):
        if receipt is None:
            return None
        start, end = receipt.get('started_ns'), receipt.get('ended_ns')
        check(start is None and end is None or integer(start) and integer(end) and end >= start,
              'experience_duration')
        return None if start is None else (end - start) / 1e9

    check(type(plan) in (bytes, str), 'experience_exact_plan_bytes_required')
    raw = plan.encode('utf-8') if type(plan) is str else plan
    plan_pin = hashlib.sha256(raw).hexdigest()
    layout = json.loads(raw)
    check(type(layout) is dict and layout.get('schema') == 'persistent-memory.experience-plan.v1'
          and pin(layout.get('dataset_sha256')) and type(layout.get('cells')) is list
          and len(layout['cells']) == 288 and type(layout.get('episodes')) is list
          and len(layout['episodes']) == 48, 'experience_plan_denominators')
    models, arms = ('gpt-6-luna', 'gpt-6.1-sol'), ('derived', 'raw', 'none', 'withdrawn')
    cells, mapping, episodes, worlds, templates, cartesian = {}, {}, {}, set(), set(), set()
    for cell in layout['cells']:
        check(type(cell) is dict and set(cell) == {'cell_id', 'world_id', 'template_id', 'model', 'repetition', 'arm'}
              and all(type(cell[k]) is str and cell[k] for k in ('cell_id', 'world_id', 'template_id'))
              and cell['cell_id'] not in cells and cell['model'] in models
              and type(cell['repetition']) is int and cell['repetition'] in (1, 2)
              and cell['arm'] in arms, 'experience_plan_cell')
        cells[cell['cell_id']] = cell
        worlds.add(cell['world_id']); templates.add(cell['template_id'])
        check(cell['world_id'] in (cell['template_id'] + '-FR', cell['template_id'] + '-EN'),
              'experience_plan_language')
    check(len(worlds) == 12 and len(templates) == 6, 'experience_plan_families')
    for episode in layout['episodes']:
        check(type(episode) is dict and set(episode) == {'episode_id', 'world_id', 'a_cell_id', 'extract_cell_id', 'b_cell_ids'}
              and type(episode['episode_id']) is str and episode['episode_id'] not in episodes
              and type(episode['b_cell_ids']) is dict and set(episode['b_cell_ids']) == set(arms),
              'experience_plan_episode')
        ids = [(episode['a_cell_id'], 'A', 'none'), (episode['extract_cell_id'], 'extract', 'none')]
        ids += [(episode['b_cell_ids'][arm], 'B', arm) for arm in arms]
        check(all(type(cid) is str and cid in cells and cid not in mapping for cid, _, _ in ids)
              and len({cid for cid, _, _ in ids}) == 6, 'experience_plan_episode_join')
        first = cells[ids[0][0]]
        identity = (first['world_id'], first['model'], first['repetition'])
        check(identity not in cartesian and episode['world_id'] == first['world_id'], 'experience_episode_duplicate')
        cartesian.add(identity)
        for cid, kind, arm in ids:
            cell = cells[cid]
            check((cell['world_id'], cell['model'], cell['repetition']) == identity
                  and cell['template_id'] == first['template_id'] and cell['arm'] == arm,
                  'experience_episode_metadata')
            mapping[cid] = (episode['episode_id'], kind)
        episodes[episode['episode_id']] = episode
    check(len(mapping) == 288 and cartesian == {(w, m, r) for w in worlds for m in models for r in (1, 2)},
          'experience_plan_cartesian')
    check(type(observations) is dict and observations.get('schema') == 'persistent-memory.experience-observations.v1'
          and observations.get('dataset_sha256') == layout['dataset_sha256']
          and observations.get('plan_sha256') == plan_pin and observations.get('mode') in ('paid', 'fake')
          and type(observations.get('rows')) is list and len(observations['rows']) == 288
          and type(observations.get('episodes')) is list, 'experience_observation_scope')
    fake = observations['mode'] == 'fake'
    check(observations.get('fake_proof_only') is fake, 'experience_fake_provenance')
    summaries = {}
    for summary in observations['episodes']:
        check(type(summary) is dict and summary.get('episode_id') in episodes
              and summary['episode_id'] not in summaries and type(summary.get('status')) is str,
              'experience_summary_join')
        check(summary.get('elapsed_seconds') is None or finite(summary['elapsed_seconds']), 'experience_episode_duration')
        feedback = summary.get('A_feedback')
        if feedback is not None:
            check(type(feedback) is dict and (feedback.get('success') is None or type(feedback['success']) is bool)
                  and type(feedback.get('observed')) is dict
                  and type(feedback['observed'].get('discriminating')) is bool, 'experience_feedback')
        grade = summary.get('lesson_grade')
        if grade is not None:
            check(type(grade) is dict and all(type(grade.get(k)) is bool for k in
                  ('shape_valid', 'references_valid', 'scope_valid', 'evidence_available'))
                  and all(grade.get(k) is None or type(grade[k]) is bool for k in ('choice_correct', 'valid'))
                  and grade.get('text_semantics_graded') is False, 'experience_lesson_grade')
        summaries[summary['episode_id']] = summary
    check(fake or len(summaries) == 48, 'experience_paid_episode_denominator')
    records, seen = [], set()
    rates = {'gpt-6-luna': ('0.10', '0.50', '0.01'), 'gpt-6.1-sol': ('2', '10', '0.10')}
    for row in observations['rows']:
        check(type(row) is dict and type(row.get('cell')) is dict, 'experience_row')
        cid = row['cell'].get('cell_id')
        check(cid in cells and cid not in seen and row['cell'] == cells[cid]
              and row.get('dataset_sha256') == layout['dataset_sha256'] and row.get('plan_sha256') == plan_pin,
              'experience_row_join')
        seen.add(cid)
        eid, kind = mapping[cid]
        check(row.get('episode_id', eid) == eid and row.get('kind', kind) == kind, 'experience_row_kind')
        consume, verification = row.get('consume'), row.get('verification')
        for receipt, schema in ((consume, 'persistent-memory.experience-extraction.v1' if kind == 'extract'
                                 else 'persistent-memory.action-transfer.consume-receipt.v1'),
                                (verification, 'persistent-memory.action-transfer.verification.v1')):
            if receipt is not None:
                check(type(receipt) is dict and receipt.get('schema') == schema
                      and receipt.get('cell') == cells[cid] and receipt.get('dataset_sha256') == layout['dataset_sha256']
                      and receipt.get('plan_sha256') == plan_pin, 'experience_receipt_binding')
        if consume is not None:
            check(consume.get('mode') == observations['mode'] and consume.get('fake_proof_only') is fake
                  and type(consume.get('provider_called')) is bool and type(consume.get('status')) is str
                  and (not fake or consume['provider_called'] is False),
                  'experience_receipt_mode')
        check(row.get('terminal_category') is None or type(row['terminal_category']) is str,
              'experience_terminal_category')
        check(kind != 'extract' or verification is None, 'experience_extract_not_task_effect')
        score = None
        if kind != 'extract' and consume is not None and verification is not None:
            check(type(verification.get('task_success')) is bool and type(verification.get('effect_verified')) is bool,
                  'experience_verification_booleans')
            if consume.get('status') == 'completed' and verification['effect_verified']:
                score = verification['task_success']
                if score:
                    check(verification.get('checks', {}).get('control.json', {}).get('exact_bytes') is True,
                          'experience_positive_control')
        tokens, cost = {}, None
        usage = None if consume is None else consume.get('usage')
        if usage is not None:
            check(type(usage) is dict, 'experience_usage_object')
            for field in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                tokens[field] = usage.get(field) if integer(usage.get(field)) else None
            prompt, completion, total = (tokens[k] for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
            pd, cd = usage.get('prompt_tokens_details'), usage.get('completion_tokens_details')
            pd_ok, cd_ok = pd is None or type(pd) is dict, cd is None or type(cd) is dict
            pd, cd = pd if type(pd) is dict else {}, cd if type(cd) is dict else {}
            cached, reasoning, write = pd.get('cached_tokens', 0), cd.get('reasoning_tokens', 0), pd.get('cache_write_tokens', 0)
            tokens['cached_tokens'] = cached if integer(cached) and prompt is not None and cached <= prompt else None
            tokens['reasoning_tokens'] = reasoning if integer(reasoning) and completion is not None and reasoning <= completion else None
            tokens['cache_write_tokens'] = write if integer(write) else None
            unsupported = [pd.get('audio_tokens', 0), cd.get('audio_tokens', 0),
                           cd.get('accepted_prediction_tokens', 0), cd.get('rejected_prediction_tokens', 0)]
            known = (pd_ok and cd_ok and all(v is not None for v in tokens.values())
                     and total == prompt + completion and write == 0
                     and all(integer(v) and v == 0 for v in unsupported))
            if known:
                with localcontext() as ctx:
                    ctx.prec = 50
                    incoming, outgoing, cache = map(Decimal, rates[cells[cid]['model']])
                    cost = str(((prompt - cached) * incoming + cached * cache + completion * outgoing) / Decimal(1000000))
        writes, blocked = (consume or {}).get('writes'), (consume or {}).get('blocked')
        check(writes is None or type(writes) is list, 'experience_writes')
        check(blocked is None or type(blocked) is list, 'experience_blocked_writes')
        records.append({'cell_id': cid, 'episode_id': eid, 'kind': kind, 'model': cells[cid]['model'],
            'arm': cells[cid]['arm'], 'family': cells[cid]['template_id'], 'score': score,
            'status': (consume or {}).get('status'), 'category': row.get('terminal_category'),
            'provider_called': None if consume is None else consume['provider_called'],
            'duration_seconds': duration(consume), 'observed_tokens': tokens,
            'generation_estimate_usd': cost, 'committed_writes': None if writes is None else len(writes),
            'blocked_writes': None if blocked is None else len(blocked),
            'candidate': kind == 'extract' and (consume or {}).get('status') == 'completed'
                         and type((consume or {}).get('procedure')) is dict,
            'repeated_error': None})

    def accounting(rows):
        result = {'planned_cells': len(rows), 'provider_called': sum(r['provider_called'] is True for r in rows),
                  'provider_call_unknown': sum(r['provider_called'] is None for r in rows),
                  'generation_estimate_coverage': sum(r['generation_estimate_usd'] is not None for r in rows),
                  'duration_known_cells': sum(r['duration_seconds'] is not None for r in rows),
                  'duration_seconds_known_subtotal': sum(r['duration_seconds'] or 0 for r in rows),
                  'candidate_count': sum(r['candidate'] for r in rows)}
        for field in ('committed_writes', 'blocked_writes'):
            result[field + '_known_subtotal'] = sum(r[field] or 0 for r in rows)
            result[field + '_known_cells'] = sum(r[field] is not None for r in rows)
        result['observed_tokens'] = {k: {'known_subtotal': sum(r['observed_tokens'].get(k) or 0 for r in rows),
            'known_cells': sum(r['observed_tokens'].get(k) is not None for r in rows)}
            for k in ('prompt_tokens', 'completion_tokens', 'total_tokens', 'cached_tokens', 'reasoning_tokens', 'cache_write_tokens')}
        with localcontext() as ctx:
            ctx.prec = 50
            result['generation_estimate_usd_known_subtotal'] = str(sum(
                (Decimal(r['generation_estimate_usd']) for r in rows if r['generation_estimate_usd'] is not None), Decimal(0)))
        return result

    groups, contrasts = [], []
    indexed = {r['cell_id']: r for r in records}
    for model in models:
        for arm in arms:
            subset = [r for r in records if r['kind'] == 'B' and r['model'] == model and r['arm'] == arm]
            groups.append({'model': model, 'arm': arm, **count([r['score'] for r in subset]),
                           'families': [{'family': family, **count([r['score'] for r in subset if r['family'] == family])}
                                        for family in sorted(templates)], 'accounting': accounting(subset)})
        for baseline in ('none', 'raw'):
            pairs = [(indexed[e['b_cell_ids']['derived']]['score'], indexed[e['b_cell_ids'][baseline]]['score'])
                     for e in episodes.values() if cells[e['a_cell_id']]['model'] == model]
            observed = [int(a) - int(b) for a, b in pairs if a is not None and b is not None]
            lower = sum((int(a) if a is not None else 0) - (int(b) if b is not None else 1) for a, b in pairs) / len(pairs)
            upper = sum((int(a) if a is not None else 1) - (int(b) if b is not None else 0) for a, b in pairs) / len(pairs)
            contrasts.append({'model': model, 'comparison': 'derived-minus-' + baseline, 'planned_pairs': len(pairs),
                              'known_pairs': len(observed), 'observed_paired_mean_difference':
                              sum(observed) / len(observed) if observed else None,
                              'missing_outcome_bounds': [lower, upper]})
    feedbacks = [(summaries.get(eid) or {}).get('A_feedback') for eid in episodes]
    grades = [(summaries.get(eid) or {}).get('lesson_grade') for eid in episodes]
    episode_times = [(summaries.get(eid) or {}).get('elapsed_seconds') for eid in episodes]
    return {'schema': 'persistent-memory.experience-analysis.v1', 'dataset_sha256': layout['dataset_sha256'],
        'plan_sha256': plan_pin, 'mode': observations['mode'], 'fake_proof_only': fake,
        'planned_cells': 288, 'planned_episodes': 48, 'episode_summaries_present': len(summaries),
        'actual_model_episode_summaries': 0 if fake else len(summaries),
        'families': 6, 'worlds': 12, 'models': 2, 'repetitions': 2, 'B_arms': 4,
        'A': count([r['score'] for r in records if r['kind'] == 'A']),
        'extraction': {'planned': 48, 'completed': sum(r['status'] == 'completed' for r in records if r['kind'] == 'extract'),
            'shape_valid': count([g['shape_valid'] if g else None for g in grades]),
            'choice_correct': count([g['choice_correct'] if g else None for g in grades]),
            'well_formed_wrong_choice': sum(g is not None and g['shape_valid'] and g['choice_correct'] is False for g in grades),
            'text_semantics_graded': False},
        'A_feedback_discriminating': count([f['observed']['discriminating'] if f else None for f in feedbacks]),
        'A_feedback_success': count([f['success'] if f else None for f in feedbacks]),
        'groups': groups, 'contrasts': contrasts, 'cells': records,
        'accounting_by_phase': {kind: accounting([r for r in records if r['kind'] == kind]) for kind in ('A', 'extract', 'B')},
        'accounting': accounting(records), 'episode_wall_seconds_known_subtotal': sum(v or 0 for v in episode_times),
        'episode_wall_known_count': sum(v is not None for v in episode_times),
        'historical_generation_tariff': {'date': '2026-10-23', 'unit': 'USD_per_million_tokens',
            'model_input_output_cached': {k: list(v) for k, v in rates.items()}, 'invoice_reconciled': False},
        'reserved_usd': None, 'actual_billed_usd': None, 'complete_cost_usd': None,
        'repeated_error': {'status': 'not_measured', 'unknown': 192, 'reason': 'requires_separate_offline_B_feedback_validation'},
        'limits': {'descriptive_only': True, 'independent_episodes_assumed': False, 'confidence_interval': None,
            'p_value': None, 'bootstrap': False, 'superiority_confirmed': False, 'equal_spend_comparison': False,
            'cache_write_pricing_supported': False, 'complete_cost_measured': False, 'runtime_activated': False}}


def calculate_action_transfer(observations, fixture_raw, plan_raw, *, primary_interval):
    """Pure receipt analysis; caller hash-binds the existing primary_interval.

    fixture_raw and plan_raw are exact bytes, not reserialized dictionaries.
    observations has schema/dataset_sha256/plan_sha256/mode/rows. Each of its
    576 rows has cell/dataset_sha256/plan_sha256/consume/verification/
    emission_status/terminal_category. consume and verification are existing
    P2/P3 receipts or None. Every planned cell remains in the denominator.
    The caller must load primary_interval from volume_analysis.py SHA256
    edb74bc815cb35e56e68b7b78d2af9b76eb396b08a9e62d787e18df9ec87c7f6.
    No file, provider, credential, scorer or bootstrap implementation here.
    """
    import collections
    from decimal import Decimal
    import hashlib
    import json
    import math
    import re

    def check(condition, reason):
        if not condition:
            raise ValueError('action_analysis:' + reason)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            check(key not in result, 'duplicate_json_key')
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError('action_analysis:nonfinite_json:' + value)

    def read_pinned(raw):
        check(type(raw) is bytes and 0 < len(raw) <= 4 * 1024 ** 2, 'raw_input_bytes')
        return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite), hashlib.sha256(raw).hexdigest()

    fixture, dataset_pin = read_pinned(fixture_raw)
    plan, plan_pin = read_pinned(plan_raw)
    models = ('gpt-6-luna', 'gpt-6.1-sol')
    arms = ('memory_on', 'strong_versioned_lexical', 'full_history_bounded', 'memory_off')
    families = {'procedure', 'correction', 'revocation', 'selfcontained'}
    emissions = {'confirmed_emitted', 'confirmed_not_emitted', 'unknown', 'not_executed'}
    cell_fields = {'cell_id', 'world_id', 'template_id', 'model', 'arm', 'repetition'}
    check(callable(primary_interval), 'existing_interval_function_required')
    check(type(fixture) is dict and fixture.get('schema') == 'persistent-memory.action-transfer.fixture.v1'
          and fixture.get('synthetic') is True and type(fixture.get('worlds')) is list
          and type(fixture.get('templates')) is list and len(fixture['worlds']) == 24
          and len(fixture['templates']) == 12, 'fixture_scope')
    worlds = {}
    for world in fixture['worlds']:
        check(type(world) is dict and type(world.get('world_id')) is str and world['world_id'] not in worlds
              and world.get('family') in families and world.get('language') in ('FR', 'EN')
              and type(world.get('template_id')) is str, 'world_binding')
        worlds[world['world_id']] = world
    template_map = {}
    for template in fixture['templates']:
        check(type(template) is dict and type(template.get('template_id')) is str
              and template['template_id'] not in template_map and template.get('family') in families
              and type(template.get('world_ids')) is list and len(template['world_ids']) == 2, 'template_binding')
        members = [w for w in worlds.values() if w['template_id'] == template['template_id']]
        check(len(members) == 2 and {w['world_id'] for w in members} == set(template['world_ids'])
              and {w['language'] for w in members} == {'FR', 'EN'}
              and {w['family'] for w in members} == {template['family']}, 'template_world_lineage')
        template_map[template['template_id']] = template
    check(set(w['template_id'] for w in worlds.values()) == set(template_map)
          and collections.Counter(w['family'] for w in worlds.values()) == dict.fromkeys(families, 6),
          'family_denominators')
    check(type(plan) is dict and set(plan) == {'schema', 'dataset_sha256', 'cells'}
          and plan['schema'] == 'persistent-memory.action-transfer.plan.v1'
          and plan['dataset_sha256'] == dataset_pin and type(plan['cells']) is list
          and len(plan['cells']) == 576, 'plan_scope_or_dataset_pin')
    planned, grid = {}, set()
    for cell in plan['cells']:
        check(type(cell) is dict and set(cell) == cell_fields and type(cell['cell_id']) is str
              and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', cell['cell_id']) is not None
              and cell['cell_id'] not in planned and cell['world_id'] in worlds
              and cell['template_id'] == worlds[cell['world_id']]['template_id']
              and cell['model'] in models and cell['arm'] in arms
              and type(cell['repetition']) is int and 1 <= cell['repetition'] <= 3, 'planned_cell_binding')
        key = (cell['world_id'], cell['model'], cell['arm'], cell['repetition'])
        check(key not in grid, 'duplicate_planned_coordinate')
        grid.add(key)
        planned[cell['cell_id']] = cell
    check(grid == {(wid, model, arm, rep) for wid in worlds for model in models
                   for arm in arms for rep in (1, 2, 3)}, 'complete_cartesian_plan')
    check(type(observations) is dict and set(observations) == {
        'schema', 'dataset_sha256', 'plan_sha256', 'mode', 'rows'}
        and observations['schema'] == 'persistent-memory.action-transfer.observations.v1'
        and observations['dataset_sha256'] == dataset_pin and observations['plan_sha256'] == plan_pin
        and observations['mode'] in ('paid', 'fake') and type(observations['rows']) is list
        and len(observations['rows']) == 576, 'observation_scope_or_pins')
    fake = observations['mode'] == 'fake'
    rates = {'gpt-6-luna': (Decimal('0.10'), Decimal('0.50'), Decimal('0.01')),
             'gpt-6.1-sol': (Decimal('2.00'), Decimal('10.00'), Decimal('0.10'))}
    row_fields = {'cell', 'dataset_sha256', 'plan_sha256', 'consume', 'verification',
                  'emission_status', 'terminal_category'}
    joined, by_group, seen, matched = [], collections.defaultdict(list), set(), {}
    for row in observations['rows']:
        check(type(row) is dict and set(row) == row_fields and type(row['cell']) is dict, 'row_schema')
        cell = row['cell']
        cid = cell.get('cell_id')
        check(type(cid) is str and cid in planned and cid not in seen and cell == planned[cid]
              and row['dataset_sha256'] == dataset_pin and row['plan_sha256'] == plan_pin
              and row['emission_status'] in emissions and type(row['terminal_category']) is str
              and 0 < len(row['terminal_category']) <= 128, 'row_identity_or_emission')
        seen.add(cid)
        consume, verification = row['consume'], row['verification']
        score = control = None
        usage = context = latency = None
        usage_status, cost = 'missing', None
        called = None
        if consume is not None:
            check(type(consume) is dict and consume.get('schema') == 'persistent-memory.action-transfer.consume-receipt.v1'
                  and consume.get('cell') == cell and consume.get('dataset_sha256') == dataset_pin
                  and consume.get('plan_sha256') == plan_pin and consume.get('mode') == observations['mode']
                  and consume.get('fake_proof_only') is fake and type(consume.get('provider_called')) is bool
                  and consume.get('status') in ('completed', 'unavailable', 'error', 'invalidated')
                  and type(consume.get('category')) is str, 'consume_binding')
            called = consume['provider_called']
            check(row['emission_status'] in ({'confirmed_emitted', 'unknown'} if called else {'confirmed_not_emitted'}),
                  'consume_emission_contradiction')
            check(not fake or not called, 'fake_provider_called')
            check(fake or consume['status'] != 'completed' or called, 'paid_completion_without_provider')
            check(fake or consume['status'] != 'completed' or row['emission_status'] == 'confirmed_emitted',
                  'completed_response_emission_unknown')
            start, end = consume.get('started_ns'), consume.get('ended_ns')
            check(type(start) is int and type(end) is int and 0 <= start <= end
                  and type(consume.get('pid')) is int and consume['pid'] > 0, 'consume_timing_or_pid')
            first_exit = consume.get('p1_exit')
            check(type(first_exit) is dict and type(first_exit.get('pid')) is int and first_exit['pid'] > 0
                  and first_exit['pid'] != consume['pid'] and type(first_exit.get('returncode')) is int
                  and first_exit['returncode'] == 0 and type(first_exit.get('exited_ns')) is int
                  and 0 <= first_exit['exited_ns'] <= start, 'first_process_exit_boundary')
            latency = end - start
            packet, preflight = consume.get('packet'), consume.get('preflight')
            check(type(packet) is dict and packet.get('arm') == cell['arm']
                  and type(packet.get('context')) is str and type(packet.get('items')) is list
                  and len(packet['items']) <= 5 and len(packet['context']) <= 2000
                  and type(packet.get('context_chars')) is int and type(packet.get('context_utf8_bytes')) is int
                  and packet.get('context_chars') == len(packet['context'])
                  and packet.get('context_utf8_bytes') == len(packet['context'].encode('utf-8')),
                  'context_coverage_or_bound')
            check(type(preflight) is dict and type(preflight.get('full_request_bytes')) is int
                  and 0 < preflight['full_request_bytes'] <= 10240
                  and preflight.get('input_token_upper_bound') == preflight['full_request_bytes'] + 1024,
                  'request_preflight_bound')
            context = {'chars': packet['context_chars'], 'utf8_bytes': packet['context_utf8_bytes'],
                       'items': len(packet['items']), 'full_request_bytes': preflight['full_request_bytes']}
            reported = consume.get('usage')
            if reported is not None:
                check(type(reported) is dict, 'usage_object')
                valid = all(type(reported.get(k)) is int and reported[k] >= 0
                            for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
                valid = valid and reported['total_tokens'] == reported['prompt_tokens'] + reported['completion_tokens']
                if valid:
                    details = reported.get('prompt_tokens_details')
                    completion = reported.get('completion_tokens_details')
                    cached = details.get('cached_tokens') if type(details) is dict else None
                    written = details.get('cache_write_tokens') if type(details) is dict else None
                    reasoning = completion.get('reasoning_tokens') if type(completion) is dict else None
                    cached = cached if type(cached) is int and 0 <= cached <= reported['prompt_tokens'] else None
                    written = written if type(written) is int and 0 <= written <= reported['prompt_tokens'] else None
                    reasoning = reasoning if type(reasoning) is int and 0 <= reasoning <= reported['completion_tokens'] else None
                    if cached is not None and written is not None and cached + written > reported['prompt_tokens']:
                        cached = written = None
                    usage = {k: reported[k] for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
                    usage.update(cached_tokens=cached, cache_write_tokens=written, reasoning_tokens=reasoning)
                    detail_valid = (type(details) is dict and type(completion) is dict
                        and cached is not None and written is not None and reasoning is not None
                        and all(type(details.get(k)) is int and details[k] >= 0 for k in ('cached_tokens', 'cache_write_tokens', 'audio_tokens'))
                        and all(type(completion.get(k)) is int and completion[k] >= 0 for k in
                                ('reasoning_tokens', 'audio_tokens', 'accepted_prediction_tokens', 'rejected_prediction_tokens')))
                    detail_valid = detail_valid and cached + written <= reported['prompt_tokens'] and reasoning <= reported['completion_tokens']
                    priceable = detail_valid and all(details[k] == 0 for k in ('cache_write_tokens', 'audio_tokens'))
                    priceable = priceable and all(completion[k] == 0 for k in ('audio_tokens', 'accepted_prediction_tokens', 'rejected_prediction_tokens'))
                    usage_status = 'complete_priceable' if priceable else 'tokens_known_tariff_or_details_unknown'
                    if priceable and called:
                        inp, out, cache = rates[cell['model']]
                        cost = ((reported['prompt_tokens'] - cached) * inp + cached * cache
                                + reported['completion_tokens'] * out) / Decimal(1000000)
                else:
                    usage_status = 'invalid_or_incomplete_reported_usage'
            if not called:
                check(reported is None, 'usage_without_provider_emission')
                usage_status = 'not_emitted'
        else:
            check(verification is None and row['emission_status'] in emissions, 'verifier_without_consumer')
        if row['emission_status'] == 'not_executed':
            check(consume is None and verification is None, 'not_executed_has_receipt')
        if verification is not None:
            check(type(verification) is dict
                  and verification.get('schema') == 'persistent-memory.action-transfer.verification.v1'
                  and verification.get('cell') == cell and verification.get('dataset_sha256') == dataset_pin
                  and verification.get('plan_sha256') == plan_pin and verification.get('fake_proof_only') is fake
                  and type(verification.get('task_success')) is bool
                  and type(verification.get('effect_verified')) is bool
                  and verification.get('category') == row['terminal_category'], 'verification_binding')
            exit_proof = verification.get('p2_exit')
            check(type(exit_proof) is dict and exit_proof.get('pid') == consume.get('pid')
                  and type(exit_proof.get('returncode')) is int and exit_proof['returncode'] == 0
                  and type(exit_proof.get('exited_ns')) is int and type(verification.get('started_ns')) is int
                  and consume['ended_ns'] <= exit_proof['exited_ns'] <= verification['started_ns']
                  and type(verification.get('ended_ns')) is int
                  and verification['started_ns'] <= verification['ended_ns']
                  and type(verification.get('pid')) is int and verification['pid'] > 0
                  and verification['pid'] not in (consume['pid'], first_exit['pid']),
                  'actual_host_reopen_boundary')
            checks = verification.get('checks')
            check(type(checks) is dict and type(checks.get('control.json')) is dict
                  and set(checks['control.json']) == {'present', 'exact_bytes'}
                  and all(type(v) is bool for v in checks['control.json'].values()), 'positive_control_observation')
            control = all(checks['control.json'].values())
            if consume['status'] == 'completed' and verification['effect_verified']:
                score = verification['task_success']
                check(not score or control, 'success_without_positive_control')
            check(not verification['task_success'] or score is True, 'inconsistent_host_success')
        elif consume is not None:
            check(row['terminal_category'] == consume['category'], 'terminal_category_binding')
        world = worlds[cell['world_id']]
        item = {'cell_id': cid, 'world_id': cell['world_id'], 'template_id': cell['template_id'],
                'family': world['family'], 'language': world['language'], 'model': cell['model'],
                'arm': cell['arm'], 'repetition': cell['repetition'], 'success': score,
                'control_success': control, 'category': row['terminal_category'],
                'emission_status': row['emission_status'], 'provider_called': called,
                'usage_status': usage_status, 'usage': usage, 'context': context,
                'consumer_p2_ns': latency, 'estimated_generation_usd': str(cost) if cost is not None else None}
        joined.append(item)
        by_group[(cell['model'], cell['arm'])].append(item)
        matched[(cell['model'], cell['arm'], cell['world_id'], cell['repetition'])] = score
    check(seen == set(planned), 'missing_planned_observation_rows')

    def counts(rows):
        known_costs = [Decimal(r['estimated_generation_usd']) for r in rows if r['estimated_generation_usd'] is not None]
        usable = [r['usage'] for r in rows if r['usage'] is not None]
        emitted = sum(r['emission_status'] == 'confirmed_emitted' for r in rows)
        complete_cost = len(known_costs) == emitted and not any(r['emission_status'] == 'unknown' for r in rows)
        successes = sum(r['success'] is True for r in rows)
        known_sum = sum(known_costs, Decimal(0))
        return {'planned': len(rows), 'success': successes, 'failure': sum(r['success'] is False for r in rows),
                'unknown': sum(r['success'] is None for r in rows),
                'control_success': sum(r['control_success'] is True for r in rows),
                'control_failure': sum(r['control_success'] is False for r in rows),
                'control_unknown': sum(r['control_success'] is None for r in rows),
                'control_success_fraction_bounds': [sum(r['control_success'] is True for r in rows) / len(rows),
                                                     sum(r['control_success'] is not False for r in rows) / len(rows)],
                'success_fraction_bounds': [successes / len(rows), sum(r['success'] is not False for r in rows) / len(rows)],
                'categories': dict(sorted(collections.Counter(r['category'] for r in rows).items())),
                'emission_accounting': dict(sorted(collections.Counter(r['emission_status'] for r in rows).items())),
                'usage_status': dict(sorted(collections.Counter(r['usage_status'] for r in rows).items())),
                'observed_token_coverage': len(usable),
                'observed_tokens_known_subtotal': {k: sum(u[k] for u in usable) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')},
                'usage_detail_coverage': {k: sum(type(u[k]) is int for u in usable)
                                          for k in ('cached_tokens', 'cache_write_tokens', 'reasoning_tokens')},
                'observed_detail_known_subtotals': {k: sum(u[k] for u in usable if type(u[k]) is int)
                                                    for k in ('cached_tokens', 'cache_write_tokens', 'reasoning_tokens')},
                'generation_estimate_coverage': len(known_costs), 'known_generation_estimate_usd': str(known_sum),
                'generation_estimate_complete_for_emissions': complete_cost,
                'estimated_usd_per_conforming_task': str(known_sum / successes)
                    if not fake and complete_cost and successes else None,
                'consumer_p2_timing_coverage': sum(r['consumer_p2_ns'] is not None for r in rows),
                'consumer_p2_ns_known_total': sum(r['consumer_p2_ns'] for r in rows if r['consumer_p2_ns'] is not None),
                'context_coverage': sum(r['context'] is not None for r in rows),
                'context_known_subtotals': {k: sum(r['context'][k] for r in rows if r['context'] is not None)
                                          for k in ('chars', 'utf8_bytes', 'items', 'full_request_bytes')}}

    metadata = [{'case_id': w['world_id'], 'family': w['family'], 'scenario_group': w['template_id']}
                for w in sorted(worlds.values(), key=lambda w: w['world_id'])]
    contrasts = []
    allowed_statistics = {'planned_tasks', 'scenario_groups', 'families', 'point_bounds',
                          'effect_uncertainty_interval_95', 'a_one_sided_95_lower',
                          'bootstrap_samples', 'bootstrap_seed', 'method', 'tasks'}
    for model in models:
        for baseline in arms[1:]:
            scores = {wid: {'memory_on': [matched[(model, 'memory_on', wid, rep)] for rep in (1, 2, 3)],
                            'memory_off': [matched[(model, baseline, wid, rep)] for rep in (1, 2, 3)]}
                      for wid in worlds}
            statistics = primary_interval(metadata, scores, samples=10000, seed=20261023)
            check(type(statistics) is dict and statistics.get('planned_tasks') == 24
                  and statistics.get('scenario_groups') == 12 and statistics.get('families') == 4
                  and statistics.get('bootstrap_samples') == 10000 and statistics.get('bootstrap_seed') == 20261023,
                  'existing_interval_denominator')
            interval = statistics.get('effect_uncertainty_interval_95')
            check(type(interval) is list and len(interval) == 2 and all(type(v) in (int, float)
                  and math.isfinite(v) and -1 <= v <= 1 for v in interval) and interval[0] <= interval[1],
                  'existing_interval_output')
            contrasts.append({'model': model, 'arm_a': 'memory_on', 'arm_b': baseline,
                              'paired_responses': 72, 'worlds': 24, 'template_clusters': 12,
                              'repetitions_within_world': 3,
                              'statistics': {k: v for k, v in statistics.items() if k in allowed_statistics}})
    groups = [{'model': model, 'arm': arm, 'worlds': 24, 'template_clusters': 12,
               **counts(by_group[(model, arm)]),
               'families': [{'family': family, **counts([r for r in by_group[(model, arm)] if r['family'] == family])}
                            for family in sorted(families)]} for model in models for arm in arms]
    return {'schema': 'persistent-memory.action-transfer.analysis.v1', 'mode': observations['mode'],
            'model_success_measured': not fake and any(r['success'] is not None for r in joined),
            'dataset_sha256': dataset_pin, 'plan_sha256': plan_pin,
            'planned_cells': 576, 'worlds': 24, 'template_clusters': 12, 'families': 4, 'repetitions': 3,
            'groups': groups, 'contrasts': contrasts, 'episodes': sorted(joined, key=lambda r: r['cell_id']),
            'overall': counts(joined), 'actual_billed_usd': None,
            'historical_price_date': '2026-10-23',
            'historical_standard_usd_per_million': {model: {'input': str(rate[0]), 'output': str(rate[1]),
                                                         'cached_input': str(rate[2])}
                                                   for model, rate in rates.items()},
            'cost_scope': 'Reported generation usage only; no invoice, judge, retrieval, storage, infrastructure or human cost.',
            'interval_source_required_sha256': 'edb74bc815cb35e56e68b7b78d2af9b76eb396b08a9e62d787e18df9ec87c7f6',
            'interval_source_binding': 'Caller must hash-bind the injected existing primary_interval before this pure function.',
            'limits': {'new_winning_gate': False, 'quality_noninferiority_confirmed': False,
                       'equal_spend_comparison': False, 'dominance_claimed': False,
                       'autonomous_learning_claimed': False, 'invoice_known': False,
                       'reasoning_is_subset_of_completion': True, 'unsupported_cache_write_not_priced': True,
                       'unknown_usage_not_zero': True, 'financial_exposure_or_refund_inferred': False,
                       'latency_scope': 'P2 process duration only; not full P1-to-P3 wall time or provider-only latency.'}}


ACTION_REPORT_FIXTURE_SHA256 = '0313a0c2e237d2220cecac6094fb68b9885810680fcea942af9f84dd20da6c88'
ACTION_REPORT_PLAN_SHA256 = '3a4f2d213ad20596c0810009cf022e530ca71ee7392af9a1dec6655374998c31'
ACTION_REPORT_INTERVAL_SHA256 = 'edb74bc815cb35e56e68b7b78d2af9b76eb396b08a9e62d787e18df9ec87c7f6'
ACTION_REPORT_CALCULATION_SHA256 = '139302066f6826f5708607920f347e8022d8aa15b3fedde1c4d3a8d506c2decf'


def action_report(observations_path, observations_sha256, *, emit=True,
                  fixture_path=None, fixture_sha256=None, plan_path=None, plan_sha256=None):
    """Reproduce the prospective analysis from pinned observations, entirely offline."""
    import re

    def read(path, pin, maximum):
        if type(pin) is not str or re.fullmatch('[0-9a-f]{64}', pin) is None or path is None:
            raise ValueError('action_report:explicit_sha256_required')
        path = Path(path).absolute()
        if not path.is_file() or any(part.is_symlink() for part in (path, *path.parents)):
            raise ValueError('action_report:regular_file_without_symlinks_required')
        if not 0 < path.stat().st_size <= maximum:
            raise ValueError('action_report:input_size_limit')
        with path.open('rb') as stream:
            raw = stream.read(maximum + 1)
        if not 0 < len(raw) <= maximum or hashlib.sha256(raw).hexdigest() != pin:
            raise ValueError('action_report:input_size_or_pin_mismatch')
        return raw

    root = Path(__file__).absolute().parent
    raw = read(observations_path, observations_sha256, 64 * 1024 ** 2)
    explicit = (fixture_path, fixture_sha256, plan_path, plan_sha256)
    if any(value is not None for value in explicit):
        if not all(value is not None for value in explicit):
            raise ValueError('action_report:explicit_fixture_and_plan_require_all_four_paths_and_pins')
    else:
        fixture_path, fixture_sha256 = root / 'action-20261023' / 'FIXTURE.json', ACTION_REPORT_FIXTURE_SHA256
        plan_path, plan_sha256 = root / 'action-20261023' / 'PLAN.json', ACTION_REPORT_PLAN_SHA256
    fixture_raw = read(fixture_path, fixture_sha256, 4 * 1024 ** 2)
    plan_raw = read(plan_path, plan_sha256, 4 * 1024 ** 2)
    interval_path = root / 'validation-20261022' / 'CODE' / 'volume_analysis.py'
    interval_raw = read(interval_path, ACTION_REPORT_INTERVAL_SHA256, 4 * 1024 ** 2)
    namespace = {'__name__': '_persistent_memory_action_interval', '__file__': str(interval_path)}
    # Execute the bytes whose pin was checked, rather than rereading a loader path.
    exec(compile(interval_raw, str(interval_path), 'exec'), namespace)
    result = calculate_action_transfer(_efficiency_json(raw), fixture_raw, plan_raw,
                                      primary_interval=namespace['primary_interval'])
    result['provenance'] = {'observations_sha256': observations_sha256,
                            'fixture_sha256': fixture_sha256,
                            'plan_sha256': plan_sha256,
                            'interval_source_sha256': ACTION_REPORT_INTERVAL_SHA256,
                            'qualified_calculation_source_sha256': ACTION_REPORT_CALCULATION_SHA256}
    if emit:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action-report', type=Path, help='Analyse pinned action-transfer observations offline.')
    parser.add_argument('--action-report-sha256', help='SHA-256 of the explicit action-transfer observations file.')
    parser.add_argument('--action-transfer', action='store_true', help='Run one pinned prospective action-transfer cell or child phase.')
    parser.add_argument('--action-phase', choices=('observe', 'propose', 'verify', 'extract'), help='Internal phase over a pinned projection only.')
    parser.add_argument('--action-cell-id', help='Select exactly one cell from the complete frozen plan.')
    parser.add_argument('--action-mode', dest='action_provider_mode', choices=('fake', 'paid'), default='fake',
                        help='Explicit literal fake response, or a separately admitted cell-bound paid grant.')
    for flag in ('action-fixture', 'action-plan', 'action-input', 'action-output', 'action-state', 'action-artifacts',
                 'action-prior-receipt', 'action-prior-exit', 'action-fake-response', 'action-grant',
                 'action-provider-source', 'action-credential-reader-source', 'action-extraction',
                 'action-verification', 'action-feedback', 'action-extraction-exit', 'action-ledger'):
        parser.add_argument('--' + flag, type=Path)
    for flag in ('action-fixture-sha256', 'action-plan-sha256', 'action-input-sha256',
                 'action-prior-receipt-sha256', 'action-prior-exit-sha256',
                 'action-fake-response-sha256', 'action-grant-sha256', 'action-extraction-sha256',
                 'action-verification-sha256', 'action-feedback-sha256', 'action-extraction-exit-sha256'):
        parser.add_argument('--' + flag)
    parser.add_argument('--efficiency', action='store_true', help='Reanalyse pinned Fresh100 usage and frozen quality offline (post-hoc).')
    parser.add_argument('--efficiency-inputs', type=Path, help='Explicit pinned efficiency manifest; requires --efficiency-inputs-sha256.')
    parser.add_argument('--efficiency-inputs-sha256', help='SHA-256 of an explicit efficiency manifest.')
    parser.add_argument('--trajectories', type=int, help='Run 1..3000 seeded core transition trajectories.')
    parser.add_argument('--compare-transitions', action='store_true', help='Compare three lifecycle arms against the frozen synthetic oracle.')
    parser.add_argument('--comparison-fixture', type=Path, help='Explicit lifecycle fixture (default: packaged frozen fixture).')
    parser.add_argument('--variants', type=int, help='Lifecycle variants per scenario: 1..10 (default 10).')
    parser.add_argument('--lance-hybrid', action='store_true',
                        help='Run the optional local synthetic LanceDB binding demo.')
    parser.add_argument('--documents', type=int, help='Typed volume mode: 1..5000 synthetic sources (default 24).')
    parser.add_argument('--repetitions', type=int, help='Typed volume mode: 1..100000 retrievals (default 10).')
    parser.add_argument('--seed', type=int, help='Typed volume mode: query seed 0..2^64-1 (default 0).')
    parser.add_argument('--volume-progress', type=Path,
                        help='Write bounded phase progress and measure full typed-volume costs; Linux only.')
    parser.add_argument('--volume-profile-tail', action='store_true',
                        help='Profile only the final ten admissions of an instrumented volume run.')
    parser.add_argument('--volume-incremental-batch', type=int, default=0,
                        help='Measure a same-instance incremental cycle: 2..100 new sources; 0 disables it.')
    args = parser.parse_args()
    if args.volume_incremental_batch:
        if (args.volume_progress is None or args.documents is None or args.volume_profile_tail
                or not 2 <= args.volume_incremental_batch <= 100):
            parser.error('--volume-incremental-batch requires --volume-progress, explicit --documents, '
                         'batch 2..100 and no --volume-profile-tail')
    elif args.volume_incremental_batch != 0:
        parser.error('Expected --volume-incremental-batch 0 or 2..100')
    if args.volume_profile_tail and args.volume_progress is None:
        parser.error('--volume-profile-tail requires --volume-progress')
    if args.volume_progress is not None:
        import sys
        if (sys.platform != 'linux' or args.documents is None or args.action_transfer
                or args.action_report is not None or args.action_report_sha256 is not None
                or args.efficiency or args.trajectories is not None or args.compare_transitions
                or args.lance_hybrid):
            parser.error('--volume-progress requires Linux and an explicit --documents typed-volume run')
    action_values = [value for key, value in vars(args).items()
                     if key.startswith('action_') and key not in (
                         'action_transfer', 'action_provider_mode', 'action_report', 'action_report_sha256')]
    if args.action_report is not None or args.action_report_sha256 is not None:
        import sys
        if args.action_report is None or args.action_report_sha256 is None:
            parser.error('--action-report and --action-report-sha256 are both required')
        report_input_keys = {'action_fixture', 'action_fixture_sha256', 'action_plan', 'action_plan_sha256'}
        forbidden_action_values = [value for key, value in vars(args).items()
                                   if key.startswith('action_') and key not in report_input_keys
                                   | {'action_transfer', 'action_provider_mode', 'action_report', 'action_report_sha256'}]
        if (args.action_transfer or any(value is not None for value in forbidden_action_values)
                or any(argument.startswith('--') and '--action-mode'.startswith(argument.split('=', 1)[0])
                       for argument in sys.argv[1:])
                or args.efficiency or args.efficiency_inputs is not None or args.efficiency_inputs_sha256 is not None
                or args.trajectories is not None or args.compare_transitions or args.comparison_fixture is not None
                or args.variants is not None or args.lance_hybrid or args.documents is not None
                or args.repetitions is not None or args.seed is not None):
            parser.error('--action-report cannot be combined with action, provider or another mode options')
        try:
            action_report(args.action_report, args.action_report_sha256,
                          fixture_path=args.action_fixture, fixture_sha256=args.action_fixture_sha256,
                          plan_path=args.action_plan, plan_sha256=args.action_plan_sha256)
        except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
            parser.error(str(error))
        raise SystemExit(0)
    if not args.action_transfer and (any(value is not None for value in action_values) or args.action_provider_mode != 'fake'):
        parser.error('action options require --action-transfer')
    if args.action_transfer:
        if (args.efficiency or args.efficiency_inputs is not None or args.efficiency_inputs_sha256 is not None
                or args.trajectories is not None or args.compare_transitions or args.comparison_fixture is not None
                or args.variants is not None or args.lance_hybrid or args.documents is not None
                or args.repetitions is not None or args.seed is not None):
            parser.error('--action-transfer cannot be combined with another mode')
        try:
            if args.action_phase is None:
                action_transfer_cell(args)
            else:
                action_transfer_phase(args)
        except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
            parser.error(str(error))
        raise SystemExit(0)
    if not args.efficiency and (args.efficiency_inputs is not None or args.efficiency_inputs_sha256 is not None):
        parser.error('--efficiency-inputs and --efficiency-inputs-sha256 require --efficiency')
    if args.efficiency:
        if (args.trajectories is not None or args.compare_transitions or args.comparison_fixture is not None
                or args.variants is not None or args.lance_hybrid or args.documents is not None
                or args.repetitions is not None or args.seed is not None):
            parser.error('--efficiency cannot be combined with another mode')
        try:
            efficiency_analysis(args.efficiency_inputs, args.efficiency_inputs_sha256)
        except (ValueError, KeyError, TypeError, OSError) as error:
            parser.error(str(error))
        raise SystemExit(0)
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
    if args.volume_incremental_batch and (documents + args.volume_incremental_batch > 5000
                                         or repetitions < args.volume_incremental_batch):
        parser.error('Incremental cycle requires total documents <=5000 and repetitions >=batch')
    if args.trajectories is not None:
        transition_trajectories(args.trajectories, seed)
    elif args.lance_hybrid:
        lance_hybrid_demo()
    else:
        report = main(documents, repetitions, seed, volume=volume, progress_path=args.volume_progress,
                      profile_tail=args.volume_profile_tail, incremental_batch=args.volume_incremental_batch)
        if volume and not report['oracle_passed']:
            raise SystemExit(1)
