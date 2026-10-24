# Source admission costs at 1,000 records

24 October 2026 · [Français](README.fr.md) · [Results](RESULT.json) · [Complete observations](observations.json) · [Protocol](PROTOCOL.json)

A small checkpoint change reduced ingestion work in three paired runs on one Linux host. Each run created 1,000 synthetic sources, synchronized the index, performed 50 searches and 50 explicit validation reads, then checked withdrawal and index maintenance. All six runs passed the same correctness checks.

The extra checkpoint is now computed only when `expected_epoch` needs to be checked. Transaction entry and exit validation, journal integrity, dependency checks and compare-and-swap behavior remain in place. It adds no validation cache. [Source pins](SOURCE-PINS.json) identify the previous core `35dd711a…`, candidate `76dba2b1…`, their dependent hash bindings and the unchanged benchmark CLI.

## Paired results

Each pair uses a fresh process and database for each arm. A is the previous core; B is the candidate. CPU is user plus system time between the first ingestion boundary and the final validation boundary.

| Pair | Order | Instrumented elapsed A → B | Ingestion A → B | CPU A → B |
| --- | --- | ---: | ---: | ---: |
| 1 | AB | 72.107 → 56.379 s | 55.046 → 39.298 s | 35.989 → 28.131 s |
| 2 | BA | 71.771 → 55.629 s | 54.540 → 38.878 s | 35.807 → 27.777 s |
| 3 | AB | 72.482 → 56.293 s | 55.110 → 39.077 s | 36.163 → 28.089 s |

Median paired reductions were **22.33% in elapsed time** (range 21.81–22.49%), **28.72% in ingestion** (28.61–29.09%) and **22.33% in CPU time** (21.84–22.42%). Elapsed time includes the benchmark's validation and telemetry. All three pairs improved on both registered performance measures, elapsed time and ingestion. No timeout or replacement was needed; the full job took 388.624 seconds.

Every run returned all 50 expected records, with no omissions, unexpected records or truncated candidates. The same query schedule was used throughout. Withdrawal still produced `index_stale` before synchronization and an empty completed result afterward. Final storage size was 2,220,171 bytes in all six runs; equal sizes do not imply identical database bytes. Memory use stayed around 35 MB at the final boundary.

## Environment and provenance

Both arms used RAM storage and the same laboratory environment. Its observed wheels were `hermes_memory_core-0.3.0a2` and `hermes_policy_registry-0.2.0a2`; three pinned module files were explicitly selected for each arm. This measures **35dd against 76db in a common 0.3.0a2 support environment**, not the performance of installed a4 distributions. The separately [qualified a4 packages](qualification.json) passed their wheel and rebuilt-source tests in two Linux environments.

The unchanged [observations](observations.json) retain preparatory draft labels. The [admission projection](ADMISSION.json) records the separate authorization issued before the exclusive launch intent. It omits the private receipt path and preserves the original hashes. No raw observation was relabeled or rerun to resolve that presentation detail.

## Reproduce the workload

Use Linux, Python with SQLite FTS5, and the existing [benchmark](../run_benchmark.py), SHA `ab92430cd614e9297d0eb18797d30bd0da012a6315705eea58620f4e911caf33`. The [protocol](PROTOCOL.json) specifies all six invocations, the fixed seed, query hash, oracle and resource limits. `--repetitions 50` means 50 searches within one run, not 50 independent full-run replications.

For a new comparison, install the current a4 core wheel into two fresh virtual environments. In environment A, replace only `core.py`, `typed_memory.py` and `typed_protocol.py` with their versions from public commit `1554beda0ef3e57621eca8974c197514302f369e`. Keep B on the current sources. Verify both sets against [SOURCE-PINS.json](SOURCE-PINS.json). Use the same benchmark file in both arms. This creates a new common environment; it does not reconstruct the archived laboratory wheel bytes.

For each cell, create a new private directory under `/dev/shm`, set `TMPDIR` to it and run the selected environment's Python:

```sh
TMPDIR=/dev/shm/your-new-private-cell \
  /path/to/selected-venv/bin/python -I -B benchmarks/run_benchmark.py \
  --documents 1000 --repetitions 50 --seed 20261021 \
  --volume-progress /path/to/new-cell-progress.json > new-cell-result.json
```

Run sequentially in order AB/BA/AB. The archived envelope was one 1,200-second unit, CPU quota 50%, memory limit 1 GiB, swap disabled, 64 tasks maximum and no network, with 180 seconds per child. Kill and wait for an over-limit child before cleaning its owned RAM directory. Preserve timeouts and unstarted cells; do not substitute runs. Compare all three pairs only after the same correctness oracle passes. The existing CLI runs the workload; the deployment operator is not required to use the library.

Three pairs are descriptive observations, not a robust population distribution or a significance test. Cold cache was not controlled. No 5,000-source result, semantic ranking quality, production latency, infrastructure cost or energy saving is established. The [earlier serialization study](../efficiency-20261023/core-optimization-20261023/README.md) used a different, uncontrolled storage setup; its percentages are not combined with these results.
