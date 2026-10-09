# Persistent Memory for AI Agents

Persistent Memory contains two independently installable Python packages: the memory core described here and an [optional policy registry](PACKAGES.md). The technical package names remain `hermes-memory-core` and `hermes-policy-registry`.

[Français](README.fr.md) · [API and service](docs/API.md) · [Recovery contract](docs/RECOVERY.md) · [Contributing](CONTRIBUTING.md)

Versioned memory for applications and agents that need to know **which evidence a result depends on, whether it is still current, and what happens after a withdrawal or an old backup is restored**.

Python 3.11+, SQLite with FTS5, standard library only. Linux is the qualified platform. No model, weights, account, external database, or persistent server is required. This is an alpha library; the repository contains synthetic examples and reusable code, not a private memory system or its data.

## Try the complete example

From this source distribution, in a fresh environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/hermes-memory-demo --directory /tmp/hermes-memory-example
```

Use a new directory. Actor A registers two synthetic evidence sources and a dependent handoff. Actor B reopens the store, withdraws one source, and verifies that the dependent handoff is denied while the unrelated source remains readable. An old content backup is then restored against the retained current authority: it starts in quarantine and cannot resurrect withdrawn evidence after validation.

The output reports each checked invariant. It does **not** claim physical erasure, model unlearning, or protection when the store, authority and freshness witness are all rolled back together.

## Use the library

```python
from pathlib import Path
from hermes_memory import Authority, Memory
from hermes_memory.typed_memory import TypedMemory

root = Path("example-state")
root.mkdir()
authority = Authority.create(root / "authority.db", root / "witness.json")
memory = Memory.create(root / "content.db", authority)
typed = TypedMemory(memory, root / "search.db")
ref = typed.put("demo", "checklist", "Copper repair checklist.", {
    "evidence_kind": "procedure", "preconditions": {"power_off": True}
})["ref"]
typed.sync("demo")  # explicit, bounded index rebuild
result = typed.search("demo", "copper", conditions={"power_off": True},
                      max_context_chars=1000)
assert result["items"][0]["ref"] == ref
```

Refs include a workspace, stable artifact identity and immutable version. Updates use compare-and-swap. Derived records declare exact parent refs. Reads revalidate current versions and withdrawals; the search index is a disposable candidate projection, never an authority.

Typed envelopes support `document`, `observation`, `hypothesis`, `procedure`, `task` and `feedback`; explicit validity intervals, aliases and exact preconditions; FTS5 lexical candidates; a character budget; and coverage/exclusion details. A hypothesis remains a hypothesis. Declared confidence is not a learned quality score or a ranking weight.

The typed policy is the frozen R3 implementation. Its bounded synthetic comparison improved evidence selection but exceeded its registered relative latency gate. No production speed improvement, semantic search, graph inference, historical-version search, or automatic learning is claimed. Experimental R4 is not included.

## CLI, optional HTTP and MCP

`hermes-memory` provides initialization, core RPC, a synthetic demo, HTTP and MCP stdio. `hermes-memory-typed` provides explicit typed admission, synchronization, context and optional serving. See [API.md](docs/API.md) for copyable local commands.

The typed HTTP routes and client are read-only; the optional combined server also exposes the **privileged core `/rpc` API** under the same token. It is intended for a trusted application boundary, not an untrusted multi-tenant deployment. Workspace names are logical partitions, not user ACLs. No public vector backend adapter is advertised; generic core projections retain exact refs but are not Qdrant or LanceDB integrations.

## Verify from an installed wheel

```sh
python -m pip install build
python -m build
python3 -m venv /tmp/hermes-memory-check
/tmp/hermes-memory-check/bin/python -m pip install dist/hermes_memory_core-0.2.0a1-py3-none-any.whl
SOURCE="$PWD"
cd /tmp
/tmp/hermes-memory-check/bin/python -m unittest discover -s "$SOURCE/tests" -v
/tmp/hermes-memory-check/bin/python "$SOURCE/benchmarks/run_benchmark.py"
```

The test sources stay outside the installed package; imports resolve to the wheel. The suite retains 47 core, 35 typed retrieval and 36 portable integration tests, plus separate product tests. A private application's AST wiring test is deliberately absent and is not counted as public coverage. [TESTING.md](docs/TESTING.md) describes provenance and boundaries.

The benchmark uses 24 generated notes and reports observations, not a universal speed score. No corpus scan, model download, or network service is involved.

## Design boundaries

- A current external authority and retained freshness witness are required for safe recovery; keep them outside content-only snapshots.
- Missing or stale dependencies produce explicit failure states. Empty results are not a substitute for unavailable authority.
- Index rebuilding and admission are explicit and bounded. No automatic ingestion or historical corpus migration occurs.
- Context budgets count Python characters, not tokens. R3 can replay authority history per operation; it is not optimized for unrestricted corpus growth.
- Revocation controls future reads through this library. It cannot recall text already copied elsewhere.
- The application decides consent, retention, user permissions, trusted storage and backup policy.

MIT license. File selection and packaging transformations are recorded in `PROVENANCE.json`. The optional policy registry is a separate distribution; see [PACKAGES.md](PACKAGES.md). It does not activate policies or grant runtime permissions.
