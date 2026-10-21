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

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lance-hybrid', action='store_true',
                        help='Run the optional local synthetic LanceDB binding demo.')
    parser.add_argument('--documents', type=int, help='Typed volume mode: 1..5000 synthetic sources (default 24).')
    parser.add_argument('--repetitions', type=int, help='Typed volume mode: 1..100000 retrievals (default 10).')
    parser.add_argument('--seed', type=int, help='Typed volume mode: query seed 0..2^64-1 (default 0).')
    args = parser.parse_args()
    volume = any(value is not None for value in (args.documents, args.repetitions, args.seed))
    if args.lance_hybrid and volume:
        parser.error('--lance-hybrid cannot be combined with typed volume options')
    documents = 24 if args.documents is None else args.documents
    repetitions = 10 if args.repetitions is None else args.repetitions
    seed = 0 if args.seed is None else args.seed
    if not 1 <= documents <= 5000 or not 1 <= repetitions <= 100000 or not 0 <= seed < 2 ** 64:
        parser.error('Expected documents 1..5000, repetitions 1..100000 and seed 0..2^64-1')
    if args.lance_hybrid:
        lance_hybrid_demo()
    else:
        report = main(documents, repetitions, seed, volume=volume)
        if volume and not report['oracle_passed']:
            raise SystemExit(1)
