# Core 0.3.0a5: qualification and archives

[Français](README.fr.md) · [Receipt](QUALIFICATION.json) · [Checksums](SHA256SUMS) · [Release](https://github.com/Musyg/persistent-memory/releases/tag/v0.3.0a5)

The installed core and optional registry passed 215 distinct test methods in two Linux environments, from wheels and wheels rebuilt from source archives. That is 430 executions per environment, 860 in total, with no failures, errors or skips. Source parity, installed imports, the portfolio example and co-installation were also checked.

The release uses the exact archives from one qualified build. A bookkeeping error in the laboratory wrapper occurred after the tests; the remaining source and archive checks were completed in a separate read-only inspection. The wrapper failure remains recorded. The archives and original test results are unchanged; the tests were not rerun during this inspection.

Archive documentation reflects the state before qualification. This receipt and the current repository record its completion without rebuilding the released artifacts. The changes concern equivalent identifier validation and its bindings. [Paired performance measurements](../../../benchmarks/efficiency-20261026/README.md) cover the fixed synthetic workload.
