# Persistent Memory for AI Agents

Persistent Memory contains two independently installable Python packages: the memory core described here and an [optional policy registry](PACKAGES.md). The technical package names remain `hermes-memory-core` and `hermes-policy-registry`. The optional registry 0.2.0a2 also assesses versioned workflow effects with independent host verification; see [packages and releases](PACKAGES.md).

[Français](README.fr.md) · [API and service](docs/API.md) · [Recovery contract](docs/RECOVERY.md) · [Contributing](CONTRIBUTING.md) · [Testing and reproducibility](docs/TESTING.md)

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

## Render reviewed facts and control the handoff

The optional [structured renderer](docs/STRUCTURED.md) turns explicitly reviewed facts into finite French templates, preserves source spans and versions, and checks a word/citation contract. The [admission boundary](docs/ADMISSION.md) adds a host-reviewed dependency dossier, authority checks before preparation and handoff, useful notices, and explicit delivery outcomes.

```sh
python -m hermes_memory.admission_demo
```

This synthetic example covers a reviewed card, unknown/conflicting evidence, withdrawal, missing authority, a changed buffer, an unmet word limit, and an effect without acknowledgment. These synchronous APIs are opt-in. They do not extract facts from arbitrary briefs or verify semantic truth. A sink acknowledgment is not downstream consumption; authority and publication are not atomic. See the linked contracts before integrating a real authority or consumer.

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

The typed policy retains the R3 retrieval contract with optional exact-reference rendering. Its bounded synthetic comparison improved evidence selection but exceeded its registered relative latency gate. No production speed improvement, semantic search, graph inference, historical-version search, or automatic learning is claimed. Experimental R4 is not included.

Set `render_source_references=True` in `TypedMemory.search` to append each validated immutable ref to its complete text. The full text, JSON ref and separators share the character budget; an item that does not fit is excluded intact. Plain text remains the default.

## CLI, optional HTTP and MCP

`hermes-memory` provides initialization, core RPC, a synthetic demo, HTTP and MCP stdio. `hermes-memory-typed` provides explicit typed admission, synchronization, context and optional serving. See [API.md](docs/API.md) for copyable local commands.

The Python server API adds `make_server(..., typed_only=True)` to expose only the authenticated typed POST routes; core `/rpc`, `/validate` and GET routes are refused. Configure `Policy(render_source_references=True)` and `Client(..., render_source_references=True)` together when using referenced contexts. These options bind a configured workspace and bearer token; they do not authenticate a person or voice. See [API.md](docs/API.md).

The typed HTTP routes and client are read-only; the optional combined server also exposes the **privileged core `/rpc` API** under the same token. It is intended for a trusted application boundary, not an untrusted multi-tenant deployment. Workspace names are logical partitions, not user ACLs. No public vector backend adapter is advertised; generic core projections retain exact refs but are not Qdrant or LanceDB integrations.

## Verify from an installed wheel

```sh
python -m pip install build
python -m build
python3 -m venv /tmp/hermes-memory-check
/tmp/hermes-memory-check/bin/python -m pip install dist/hermes_memory_core-0.3.0a4-py3-none-any.whl
SOURCE="$PWD"
cd /tmp
/tmp/hermes-memory-check/bin/python -m unittest discover -s "$SOURCE/tests" -v
/tmp/hermes-memory-check/bin/python "$SOURCE/benchmarks/run_benchmark.py"
```

The test sources stay outside the installed package; imports resolve to the wheel. The memory package has 160 public tests and the optional policy registry has 49. Version 0.3.0a4 was qualified from installed wheels and rebuilt source distributions in two Linux environments. A private application's AST wiring test is deliberately absent and is not counted as public coverage. [TESTING.md](docs/TESTING.md) describes provenance and boundaries.

The benchmark uses 24 generated notes and reports observations, not a universal speed score. No corpus scan, model download, or network service is involved.

The optional [synthetic LanceDB demonstration](docs/BENCHMARK-LANCE.md) exercises explicit vector/text retrieval and current-version/withdrawal checks with predefined vectors. It uses separate optional dependencies; the default benchmark remains unchanged.

## Design boundaries

- A current external authority and retained freshness witness are required for safe recovery; keep them outside content-only snapshots.
- Missing or stale dependencies produce explicit failure states. Empty results are not a substitute for unavailable authority.
- Index rebuilding and admission are explicit and bounded. No automatic ingestion or historical corpus migration occurs.
- Context budgets count Python characters, not tokens. R3 can replay authority history per operation; it is not optimized for unrestricted corpus growth.
- Revocation controls future reads through this library. It cannot recall text already copied elsewhere.
- The application decides consent, retention, user permissions, trusted storage and backup policy.

MIT license. File selection and packaging transformations are recorded in `PROVENANCE.json`. The optional policy registry is a separate distribution; see [PACKAGES.md](PACKAGES.md). It does not activate policies or grant runtime permissions.

## Observed memory on/off comparison

The [confirmation study](benchmarks/validation-20261022/README.md) covers 100 distinct synthetic scenarios, with three repetitions for each model and condition: all 1,500 answers were delivered and all 3,000 AI judge responses completed. GPT-6 Luna succeeded on 298/300 answers with memory (99.33%), versus 29/300 without; GPT-6.1 Sol reached 300/300 versus 30/300. Luna’s primary gain was 89.67 percentage points, with a nominal 95% interval of 89–90 points and a one-sided 95% lower success bound of 98%. Lexical retrieval succeeded on 294/300: the 95% memory/lexical effect interval, −0.33 to +3.33 points, does not establish superiority.

The study page is the canonical account of methods, failures, limits and offline recalculation. These short, structured scenarios were assessed by two AI judges, without an external human quality audit. The [earlier 500-task campaign and evaluator erratum](benchmarks/validation-20261021/README.md), [technical reliability and load results](benchmarks/validation-20261021/TECHNICAL/README.md), and [eight-task exploratory application pilot](docs/MEMORY-COMPARISON.md) provide separate evidence; their counts and scope are not combined with this confirmation study.

The separate [lifecycle comparison](benchmarks/lifecycle-20261022/README.md) replays 100 fixed trajectories on three implementations in two Linux environments. Hermes and SQLite with retained authority both preserve all 751 valid reads and block all 389 forbidden reads per run; restoring old authority with old content exposes 82 withdrawn or superseded records. The main comparison is a tie on these guarantees, with complete synthetic observations available for inspection and reproduction.

The [secondary efficiency analysis](benchmarks/efficiency-20261023/README.md) links all 1,500 historical answers to their reported usage. Luna with memory used 4.70% fewer tokens and 3.75% less estimated generation cost than lexical retrieval, with slightly higher p95 and inconclusive quality superiority. This is an observed footprint, not a matched-spend or general dominance claim; the analysis makes no new provider requests.

The [artifact action study](benchmarks/action-20261023/README.md) verifies CSV/JSON effects across three separate processes. Across 24 worlds drawn from 12 templates, Luna with memory passed 66/72 tasks versus 35/72 without memory, with one unavailable response in that latter arm; Sol passed 72/72 versus 36/72. Versioned lexical retrieval scored 67/72 and 72/72, so superiority over that baseline is not established. Synthetic observations, initial failures, calibration and the protocol amendment are retained with reproduction commands.

The [core optimization study](benchmarks/efficiency-20261023/core-optimization-20261023/README.md) measures the same 1,000-source workload before and after a small serialization change. Instrumented workload time fell by 28.01% and 27.68% on two Linux hosts, with identical checked outcomes and storage size. Eight real process-kill trajectories also passed. These are single observations per host, not a production latency or general scaling guarantee.

The [paired admission benchmark](benchmarks/efficiency-20261024/README.md) compares a source-admission checkpoint change with the previous core across three pairs of fresh processes. At 1,000 synthetic sources and 50 searches per run on common RAM storage, median paired reductions were 22.33% in instrumented elapsed time, 28.72% in ingestion time and 22.33% in CPU time. All six runs passed the same correctness checks. These are descriptive results from one Linux host, not a production or general scaling claim.

The [incremental memory cycle](benchmarks/efficiency-20261025/README.md) separates the cost of loading 1,000 synthetic sources from the subsequent work: adding and reading ten sources, synchronizing, searching, then checking withdrawal and a valid control. The study compares the same two cores in three pairs of fresh processes; its report keeps setup and marginal costs separate, with the protocol, observations and limits available for inspection. The benchmark CLI is provided by this Git revision; the a4 release archives remain unchanged.

The [learned-experience study](benchmarks/action-20261023/experience/README.md) executes A, extracts a lesson from its real outcome, then applies it to a different B task in a fresh process. Across 288 calls, Luna succeeded on 22/24 B tasks with the derived lesson, versus 13/24 with the complete trace and 7/24 without experience. Sol scored 24/24 with either the lesson or trace, versus 12/24 without experience. The files produced by all 192 B tasks were independently reopened and verified. The study reports construction overhead, failures and limits, with [offline reproduction](benchmarks/action-20261023/experience/REPRODUCE.md).
