# Core allocation change and bounded crash recovery

23 October 2026 · [Français](README.fr.md) · [Measurements and receipt hashes](RESULT.json) · [Earlier generation-cost study](../README.md)

A small change to the [memory authority](../../../src/hermes_memory/core.py) reduced the elapsed time observed in the same synthetic workload on two Linux hosts. It removes redundant reference serialization, repeated JSON decoding of the same journal row and repeated validation of an already validated reference. Journal, materialized-state and retained-anchor checks still run on every transaction. There is no validation cache. Reference subclasses keep their previous serialization behavior.

## Observed workload

The existing [typed-volume benchmark](../../run_benchmark.py) ran before and after the change at 100 and 1,000 synthetic sources. Each run included ingestion, index synchronization, 50 timed searches, 50 explicit validation reads, withdrawal and index maintenance. The query schedules matched. All expected-result checks passed, with no missing or unexpected items.

At 1,000 sources:

| Linux host | Instrumented workload before | After | Observed reduction | Ingestion before → after |
| --- | ---: | ---: | ---: | ---: |
| A | 100.985 s | 72.699 s | 28.01% | 76.892 → 55.498 s |
| B | 94.704 s | 68.490 s | 27.68% | 72.248 → 52.365 s |

These are elapsed times for the instrumented workload, including validation and telemetry. There was one observation per host, size and version; cache state was not controlled. The figures describe these runs and do not establish a general speed advantage. Profiling identified the allocation work; profiled timings are excluded from this comparison.

After synchronization and withdrawal, stored file sizes were unchanged: 364,682 bytes at 100 sources and 2,220,171 bytes at 1,000. This compares sizes, not database byte identity. The JSON includes CPU time, current and peak process RSS, phase timings and method counts. At 1,000 sources, end-of-run current RSS increased from about 38.0 to 38.7 MB on A and 36.9 to 38.5 MB on B. Energy use, infrastructure price and complete cost remain unknown.

The 5,000-source case was not executed: its prospective forecast exceeded the 600-second cap. It has no measured latency, successful-result score or scalability claim here.

## Recovery after actual process termination

The updated core also passed four fixed SIGKILL trajectories on each host. Every trajectory reopened in a fresh process, refused withdrawn source A and returned valid independent source B through both the direct and typed paths.

| Interruption | Host A: kill to verified B | Host B |
| --- | ---: | ---: |
| Search interrupted during withdrawal | 0.348 s | 0.299 s |
| Index sync, delayed writer/CAS and restoration of an old content snapshot and index | 0.227 s | 0.267 s |
| Authority committed before anchor publication | 0.350 s | 0.307 s |
| Outbox projection completed before acknowledgment | 0.383 s | 0.320 s |

The interval starts when SIGKILL is sent and includes explicit synchronization or audited anchor repair plus fresh HTTP verification. The anchor gap first refused service until the explicit repair; outbox replay remained idempotent. The benchmark waited for all processes it launched and collected their exit statuses. These eight trajectories are finite laboratory observations, not RTO percentiles, an availability SLO or a hardware power-loss test.

## Scope and reproduction

No provider calls or production service actions were involved. This note summarizes archived native receipts; their hashes and the before/after core hashes are in `RESULT.json`. It does not replace or change the earlier model-generation study.

With both packages installed, run the existing volume mode from the repository root on Linux:

```sh
python -I -B benchmarks/run_benchmark.py --documents 1000 --repetitions 50 --seed 20261021 --volume-progress volume-progress.json > volume-result.json
```

New timings depend on the host and load. The archived recovery results additionally used controlled process stops, actual SIGKILL, fresh process launches and an explicit laboratory anchor audit. A normal volume run does not reproduce those interruption schedules.
