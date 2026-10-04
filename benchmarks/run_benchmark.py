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


if __name__ == '__main__':
    main()
