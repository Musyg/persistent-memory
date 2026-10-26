# Faster identifier validation with the same contract

26 October 2026 · [Français](README.fr.md) · [Measurements](measurements.json)

A focused change to identifier validation cuts instrumented runtime by a **median 6.79%** across three new paired comparisons. CPU time falls by a **median 6.77%**. All six runs return the expected results, including the checks after a source is revoked.

The implementation replaces a Python loop over individual characters with `re.search(r'[\x00-\x1f]', x)`, which finds the same control characters. The contract stays the same: an exact string type, a UTF-8 length of 1 to 512 bytes, and rejection of U+0000 through U+001F. DEL and C1 control characters remain accepted. A regression test checks all 1,114,112 Unicode code points, followed by mixed strings, byte-length boundaries and encoding exceptions. This is one regression test alongside the existing functional suite, rather than a large sample of independent tasks.

| Pair | Order | Instrumented time A → B | Reduction | CPU A → B | CPU reduction |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | AB | 116.384 → 107.498 s | 7.64% | 58.048 → 53.641 s | 7.59% |
| 2 | BA | 115.796 → 107.936 s | 6.79% | 57.768 → 53.860 s | 6.77% |
| 3 | BA | 115.686 → 108.497 s | 6.21% | 57.720 → 54.124 s | 6.23% |

A runs core `76dba2b1…`; B runs core `80c55792…`. Each cell starts a fresh process and database on the same Linux host, using the same runner and synthetic inputs. It loads 1,500 sources, adds ten more to the same memory instance, performs 50 retrieval trials, then checks reads, revocation and a valid control source. The complete workload includes 63 explicit reads and 53 searches per cell. Final observed storage is unchanged at 3,358,859 bytes.

The acceptance criteria were fixed before these six runs: all checks must pass, median instrumented runtime must fall by at least 3%, CPU time must fall in every pair, and no pair may regress by more than 2% in instrumented runtime. An earlier pilot informed this engineering threshold. Its measurements are excluded from the table and the acceptance calculation. All six planned cells completed, with no replacement or retry.

Instrumented runtime covers initial loading and the full memory cycle, including revalidation and telemetry. The CPU window runs from the start of ingestion to the end of the checks after revocation. Inclusive phases are not added to their enclosing total. Observed resource limits were 50% CPU, 1 GiB RAM, no swap, 64 tasks and a private network namespace. Process termination and temporary RAM cleanup were verified.

This study asks a specific question: does equivalent identifier validation reduce the engine's work on this workload? The three pairs consistently support that engineering decision. Full mission cost, energy use and production service latency require their own measurements. These percentages cannot be added to gains reported for earlier optimizations.

The runs used the existing a4 wheel with the exact source files for each arm overlaid in an isolated environment. They do not qualify a newly distributed archive. The measurement file records hashes for the core, runner, query schedule and decision criteria.

To reproduce the workload, use the [existing Linux recipe](../efficiency-20261025/REPRODUCE.md) to create a fresh environment, select modules and verify their imports without bytecode. Replace its version table with the A and B trios in `reproduction.module_sha256` in [the measurements](measurements.json): A comes from commit `3c5251ef4b187410fe65b71a0e5b32184199d96a`; B comes from the publication commit containing this study. Use the same a4 core wheel for both arms and check its recorded hash. At the recipe’s installation step, pass only `$CORE_WHEEL` to pip; this study uses the core package alone. The runner must hash to `a2cfda65d6df85f76670af5efb413fc3f0d3d776cd8324e5251cf3b05bfa1b02`.

Replace the recipe’s per-cell command with:

```sh
TMPDIR="$CELL_RAM" timeout --signal=KILL 170s \
  "$ENV/bin/python" -I -B "$CHECKOUT/benchmarks/run_benchmark.py" \
  --documents 1500 --repetitions 50 --seed 20261021 \
  --volume-progress "$CELL_OUTPUT/progress.json" --volume-incremental-batch 10 \
  > "$CELL_OUTPUT/result.json" 2> "$CELL_OUTPUT/stderr.log"
```

Apply the trios in the fixed order **A, B, B, A, B, A**, with a fresh process, database and RAM directory for each cell. The full unit has **1,050 s**, each child has **170 s**, and **30 s are reserved**; do not start a child after 870 s or without enough remaining time for the child and reserve. Keep the limits above, verified import records and cleanup receipts. Do not replace cells or retry automatically. Query each of the ten new sources once, then draw 40 queries from the initial 1,500 sources using seed 20261021; verify the schedule hash in the measurements. After checking every oracle, calculate each paired reduction as `1 - B/A`, then take the median. Cache state is not controlled, and new timings will depend on the host and its load.
