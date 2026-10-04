"""Two synthetic actors, exact evidence references, restart and withdrawal."""
import argparse
import json
from pathlib import Path

from .core import Authority, Memory
from .typed_memory import TypedMemory


def run(directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=False)
    authority = Authority.create(root / 'retained-authority' / 'authority.db',
                                 root / 'retained-witness' / 'checkpoint.json')
    actor_a = Memory.create(root / 'content.db', authority)
    typed_a = TypedMemory(actor_a, root / 'actor-a-index.db')
    workspace = 'hermes-typed-example'
    a = typed_a.put(workspace, 'source-A', 'Copper task: use the approved checklist.',
                    {'evidence_kind': 'procedure', 'preconditions': {'approved': True}})['ref']
    b = typed_a.put(workspace, 'source-B', 'Copper task: keep the independent blue control.',
                    {'evidence_kind': 'observation'})['ref']
    typed_a.sync(workspace)
    context = typed_a.search(workspace, 'copper', conditions={'approved': True})
    assert {item['ref']['artifact_id'] for item in context['items']} == {'source-A', 'source-B'}
    handoff = actor_a.derive(workspace, 'handoff', context['context'], 'task',
                            [{'ref': item['ref'], 'relation': 'derives'} for item in context['items']],
                            actor_a.checkpoint()['epoch'])['ref']
    actor_a.backup(root / 'old-content.db')
    # Actor B opens the same durable contract after an application restart.
    actor_b = Memory.open(root / 'content.db', Authority.open(authority.path, authority.anchor_path))
    assert actor_b.read(handoff)['allowed']
    actor_b.revoke_source(workspace, 'source-A', 'example-withdraw-A')
    assert not actor_b.read(a)['allowed'] and not actor_b.read(handoff)['allowed']
    assert actor_b.read(b)['allowed']
    restored = Memory.open(root / 'old-content.db', actor_b.authority)
    quarantined = restored.read(b)
    assert not quarantined['allowed']
    restored.restore_verify(actor_b.authority.checkpoint())
    assert not restored.read(a)['allowed'] and not restored.read(handoff)['allowed']
    assert restored.read(b)['allowed']
    typed_b = TypedMemory(restored, root / 'actor-b-index.db')
    typed_b.sync(workspace)
    after = typed_b.search(workspace, 'copper', conditions={'approved': True})
    assert [item['ref'] for item in after['items']] == [b]
    return {'synthetic': True, 'actors': ['author', 'consumer'], 'restart_read_allowed': True,
            'initial_exact_refs': [a, b], 'handoff_ref': handoff,
            'withdrawn_source_denied': True, 'dependent_handoff_denied': True,
            'old_content_restore_quarantined': True, 'fresh_authority_retained': True,
            'control_source_preserved': True, 'restored_context': after['context'],
            'physical_erasure_claimed': False}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True, help='New directory for synthetic files')
    args = parser.parse_args(argv)
    print(json.dumps(run(args.directory), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
