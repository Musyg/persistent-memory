# Operations surface

[Français](OPERATIONS.fr.md) · [README](../README.md) · [API and service](API.md)

`hermes_memory.persistent.PersistentMemory` gathers the memory's operations behind one class. Adapters (MCP, agent plugins, HTTP) are meant to call it rather than the core directly, so that each of them exposes the same memory: sources, derived artifacts with exact parents, corrections, withdrawal with cascade, lessons and withdrawal notices.

It adds no new authority. Every read still goes through `Memory.read` or `Memory.validate`; the search index and the ledger are sidecars that can be deleted and rebuilt.

## Open a store

```python
from hermes_memory.persistent import PersistentMemory

memory = PersistentMemory("state/memory", "team-notes", create=True)
```

One directory holds one store; a store can hold several workspaces. Without `create=True`, a missing store is refused (`store_missing`) instead of being created silently.

| File | Role | Can be lost? |
| --- | --- | --- |
| `authority/authority.db` | Versions, dependencies, withdrawals, event chain | No |
| `anchor/checkpoint.json` | Freshness witness, kept apart from the content | No |
| `content.db` | Content and the core lexical projection | No |
| `index.db` | Search index, rebuilt from authority | Yes |
| `ledger.db` | Exposures, notices, withdrawal reasons, lesson parents | Yes, notices are then lost |

## The operations

| # | Method | What it does |
| --- | --- | --- |
| 1 | `read(ref, session=None)` | Reads one exact version through current authority. A refusal returns the reason (`source_revoked`, `version_not_current`, `invalidated`, ...) and a reader state (`withdrawn`, `superseded`, `invalidated`, ...). |
| 2 | `search(query, kinds=None, as_of=None, conditions=None, top_k=5, max_chars=2000, session=None)` | Returns current, readable versions only. Validity windows are checked at `as_of`, now by default; items with preconditions need matching `conditions`. A query of more than eight words keeps its words of three characters or more. |
| 3 | `remember(text, kind="observation", source_id=None, aliases=None, valid_from=None, valid_until=None, observed_at=None, preconditions=None, confidence=None)` | Admits a new source. An existing `source_id` is refused with `version_conflict`: use `correct`. |
| 4 | `derive(text, parents, kind="procedure", artifact_id=None, expected_version=None, expected_epoch=None, ...)` | Stores an artifact made from exact parent versions. A parent is a ref (relation `derives`) or `{"ref": ..., "relation": "derives" \| "indexes" \| "cites"}`. At least one `derives` or `indexes` parent is required, and those parents must be readable now. |
| 5 | `correct(artifact_id, text, expected_version, parents=None, ...)` | Compare-and-swap: replaces the current version only if it is still `expected_version`. Metadata that is not given is kept. A derived artifact keeps its parents unless new ones are given; they must still be current. |
| 6 | `explain(artifact_id_or_ref)` | Metadata only: kind, readability, parents, upstream graph, versions and dependents. Never returns content. |
| 7 | `plan_withdrawal(artifact_id)`, `withdraw(artifact_id, reason, event_id=None, session=None)` | The plan lists what would be blocked. Withdrawing a source revokes every version of it (idempotent per `event_id`); withdrawing a derived artifact invalidates its current version. Either way, everything derived through `derives` or `indexes` stops being readable, and projections are purged. Nothing is physically erased. |
| 8 | `learn(trace, feedback, lesson, kind="procedure", lesson_id=None, ...)` | Stores a task trace and its feedback as raw sources, then derives the lesson from both. Only the lesson is searchable. Withdrawing the trace or the feedback blocks the lesson. If the lesson cannot be stored, both parents are revoked again. |
| 9 | `record_exposure(session, refs, via)`, `notices(session, mark=True)`, `exposure_report()` | The ledger notes which versions a session was shown (`read` and `search` record it when given `session`). `notices` returns, once each, the versions that session saw and that are no longer valid: withdrawn, invalidated or superseded by a correction. `exposure_report` lists every affected session. |

`OPERATIONS` lists the method names, for adapters that expose them.

Refusals raise `hermes_memory.core.MemoryError`, a `ValueError` whose message is the reason code. Unexpected storage errors are not converted.

## Example

```python
memory = PersistentMemory("state/memory", "team-notes", create=True)

port = memory.remember("The test server listens on port 9300.", source_id="port")
note = memory.derive("Open 9300 on the test firewall.", parents=[port["ref"]], kind="procedure")

memory.search("firewall 9300", session="chat-1")          # the session sees the procedure
memory.correct("port", "The test server listens on port 9400.",
               expected_version=port["ref"]["version_id"])

memory.read(note["ref"])["state"]                        # "superseded": its parent changed
memory.notices("chat-1")["notices"]                       # tells chat-1, once
```

A lesson from experience:

```python
out = memory.learn(
    trace={"task": "export ledger as CSV", "attempt": "UTF-8 without BOM"},
    feedback={"success": False, "violation": "bom_required"},
    lesson="For this receiver, export CSV as UTF-8 with a BOM.",
)
memory.search("CSV receiver BOM", kinds=["procedure"])   # finds the lesson, not its parents
memory.withdraw(out["feedback"]["artifact_id"], "feedback was wrong")   # the lesson is blocked
```

## Limits

- One process at a time per store is the tested case; several processes are serialized by SQLite but are not part of this surface's tests.
- The search index holds up to 5,000 current artifacts per workspace and 32 MiB of content per rebuild.
- `search` is lexical (SQLite FTS5 plus exact aliases). Vector projections arrive separately and stay revalidated against authority.
- Completeness (`complete`) is reported for the indexed candidates at the current epoch. Trace and feedback sources are left out of the index on purpose and do not make a result incomplete.
- Linux is the qualified platform for this release.
