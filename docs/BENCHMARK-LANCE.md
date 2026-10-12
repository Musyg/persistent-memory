# Optional synthetic LanceDB demonstration

[Français](BENCHMARK-LANCE.fr.md)

This example connects local hybrid retrieval to Persistent Memory's version and withdrawal checks. It uses four synthetic sources and fixed three-dimensional vectors. It has been exercised on Linux with **LanceDB 0.25.3 and PyArrow 23.0.1**.

## Run the example

Use a Linux environment with Persistent Memory installed, from the repository root. See the [installation example](../README.md#try-the-complete-example) for the core package.

The existing benchmark remains the default and does not require LanceDB:

```sh
.venv/bin/python benchmarks/run_benchmark.py
```

To use the optional demonstration, install its dependencies explicitly in that environment:

```sh
.venv/bin/python -m pip install 'lancedb==0.25.3' 'pyarrow==23.0.1'
.venv/bin/python benchmarks/run_benchmark.py --lance-hybrid
```

These libraries are optional and imported only by this mode. Once dependencies are installed, the demonstration requests no provider API, model or download. It supplies vector and text explicitly, with no embedding function or dense fallback. Errors propagate.

## What it checks

The example creates a temporary local Lance table and a native FTS index. Candidate rows carry versioned refs. Before constructing context, `Memory.validate` checks each ref against current authority and supplies the authorized envelope text; projection text is not treated as authority.

It then replaces one source version and withdraws another. `TypedMemory` rejects its stale index until explicit synchronization. The example adds the replacement row to Lance and **explicitly rebuilds the synthetic FTS index**. Two obsolete rows remain in the table so currentness validation must exclude them. This refresh is performed by the example; it is not an automatic production synchronization mechanism.

Authority checkpoints are checked before retrieval and again before returning context, with a maximum of 200 characters. The query fails if the projection checkpoint is stale or authority changes during retrieval.

| Observation | Expected result |
|---|---|
| Initial sources and eligible candidates | 4 |
| Stored projection rows after replacement | 5 |
| Eligible current candidates afterward | 3 |
| Excluded obsolete rows | `source_revoked`, `version_not_current` |
| Vector dimensions | 3 |

## Read the output

The JSON reports library versions, candidate and eligible rows, exclusion reasons, context and query elapsed time. Identifiers and timings vary between runs; the checked invariants are reproducible. Both the default invocation and this optional invocation completed successfully with the tested dependency versions.

The vectors are predefined toy values. The unrelated note remains eligible. This demonstrates explicit SDK binding and authority revalidation on a small synthetic example; ranking quality, learned memory, throughput, cold-cache behavior and general speed superiority are not measured.
