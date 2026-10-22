# Corrections, withdrawals and old-snapshot recovery

[Français](README.fr.md) · [Fixture](FIXTURE.json) · [Summary](SUMMARY.json) · [Linux A observations](LINUX-A.json) · [Linux B observations](LINUX-B.json) · [Source pins](INPUTS.json)

Hermes and an independently implemented SQLite reference with retained current authority produced **equivalent correct outcomes** on these fixed functional scenarios. Both served all 751 valid reads exactly and blocked all 389 forbidden reads in each run. A SQLite configuration that restored its old authority along with its old content exposed 82 withdrawn or superseded records. This demonstrates the value of retaining fresh authority across recovery; it does not establish superiority over a properly protected SQLite implementation or another memory product.

## Results per implementation, per Linux environment

| Observation | Hermes | SQLite, retained authority | SQLite, authority rolled back |
| --- | ---: | ---: | ---: |
| Cases satisfying the current-state oracle | 100/100 | 100/100 | 80/100 |
| Valid reads with exact expected content | 751/751 | 751/751 | 751/751 |
| Forbidden reads exposed | 0/389 | 0/389 | 82/389 |
| Withdrawn content exposed | 0/154 | 0/154 | 41/154 |
| Superseded content exposed | 0/123 | 0/123 | 41/123 |
| Reads blocked while quarantined | 92/92 | 92/92 | 92/92 |
| Missing-current-content checks without fallback | 20/20 | 20/20 | 20/20 |
| Expected semantic rejections matched | 60/60 | 60/60 | 60/60 |
| Late writes admitted | 0/40 | 0/40 | 0/40 |
| Replayed withdrawal receipts preserved | 10/10 | 10/10 | 10/10 |
| Restorations reconciled | 20/20 | 20/20 | 20/20 |
| Unexpected errors / unexecuted operations | 0 / 0 | 0 / 0 | 0 / 0 |

The four forbidden-read categories are disjoint and total 389. The same 100 cases and 2,086 operations per arm ran in two Linux environments; case order, counters and normalized observations matched. These are repetitions of one fixed protocol, not 200 independent scenarios. Each environment also passed 11 focused product tests, including the isolated CLI and evaluator negative controls. No provider requests were made.

## Protocol and fairness

The ten families cover valid controls, corrections with strong dependency chains, `indexes`, documentary `cites`, two sequential CAS intents prepared from one version, late writes after withdrawal and correction, recovery after withdrawal, recovery with current content missing, and workspace isolation. Ten explicit variants per family vary synthetic content, depth and operation order. The fixture was frozen before execution; the seed is 20261022.

One declarative executor replays the same operations on all arms. Its independent oracle names exact logical versions and expected content, including accents and punctuation. Adapters receive operation arguments, never expected results. Refusing every read, returning the wrong text, serving content despite a denied flag, or treating an arbitrary SQLite exception as a valid rejection fails the checks. Generated version/checkpoint tokens are retained in raw observations and replaced with symbolic references only in the deterministic parity view.

Both SQLite profiles implement immutable versions, current heads, tombstones, CAS, idempotent withdrawals, strong-dependency validation and workspace isolation. The main comparison gives Hermes and SQLite equally fresh authority outside content snapshots. The context arm restores both its content and authority, with no external freshness evidence: its 82 unsafe reads remain failures against the current-state oracle even though they match the deliberately weaker configuration. No implementation can detect a complete rollback of all trusted evidence without some fresher retained anchor.

## Reproduce on Linux

Install this source distribution into a fresh environment, then run from its extracted source directory:

```sh
python -m venv /tmp/lifecycle-check
/tmp/lifecycle-check/bin/pip install --no-deps .
/tmp/lifecycle-check/bin/python -I -B -m unittest discover -s tests -p test_product.py -v
/tmp/lifecycle-check/bin/python -I -B benchmarks/run_benchmark.py --compare-transitions --variants 10 --seed 20261022 > comparison.json
```

`--variants 1` is a shorter ten-case check. An explicit fixture can be supplied with `--comparison-fixture`. The historical default benchmark and `--trajectories` mode retain their earlier behavior. The support module is a benchmark reference, not a production memory service.

## Scope and diagnostic history

These are deterministic lifecycle checks through the read-by-reference API, with sequential operations and logical close/reopen. They do not test retrieval ranking, simultaneous clients, process termination, power loss, physical erasure, latency superiority or general business-task quality. Hermes-specific outbox and anchor fault injections remain separate [technical evidence](../validation-20261021/TECHNICAL/README.md), without a matched comparison here.

The first native candidate passed ten focused tests but failed to load its adjacent support module under `python -I`, before any comparative observations were produced. The repair loads that file explicitly and adds an actual isolated-CLI regression test. The fixture, independent reference and oracle were unchanged; the results here use only the repaired candidate. This study adds no production runtime change. The [memory on/off confirmation study](../validation-20261022/README.md) measures a different question and its results are not pooled with these checks.
