"""Small synthetic index/revalidation exercise, not a production speed claim."""
import json
from pathlib import Path
import statistics
import tempfile
import time

from hermes_memory import Authority, Memory
from hermes_memory.typed_memory import TypedMemory


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        authority = Authority.create(root / 'authority.db', root / 'anchor.json')
        memory = Memory.create(root / 'memory.db', authority)
        typed = TypedMemory(memory, root / 'index.db')
        refs = []
        for index in range(24):
            refs.append(typed.put('example', 'note-' + str(index),
                                  'Synthetic copper item number ' + str(index),
                                  {'evidence_kind': 'observation'})['ref'])
        typed.sync('example')
        timings = []
        for _ in range(10):
            start = time.perf_counter()
            result = typed.search('example', 'copper', top_k=5, max_context_chars=200)
            timings.append(time.perf_counter() - start)
            assert result['status'] == 'completed' and len(result['context']) <= 200
            assert all(memory.read(item['ref'])['allowed'] for item in result['items'])
        memory.revoke_source('example', 'note-0', 'example-revoke-0')
        stale = typed.search('example', 'copper')
        assert stale['status'] != 'completed'
        typed.sync('example')
        after = typed.search('example', 'copper')
        assert all(item['ref'] != refs[0] for item in after['items'])
    print(json.dumps({'synthetic_documents': 24, 'repetitions': 10, 'median_seconds': statistics.median(timings),
                      'max_seconds': max(timings), 'revocation_checked': True,
                      'cold_cache_controlled': False, 'general_speed_superiority_claimed': False}, indent=2))



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
    args = parser.parse_args()
    if args.lance_hybrid:
        lance_hybrid_demo()
    else:
        main()
