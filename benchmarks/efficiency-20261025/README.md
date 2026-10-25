# Memory cycle costs after the initial load

25 October 2026 · [Français](README.fr.md) · [Measurements, calculations and hashes](RESULT.json) · [Observations](observations.json) · [Protocol](PROTOCOL.json) · [Reproduce](REPRODUCE.md)

After loading 1,000 sources, the memory cycle took less time with core `76dba2b1…` in all three paired comparisons. The observed median reduction was **2.35%**, or **0.458 seconds**, with a range of 1.67–2.69%. The initial load showed a separate median reduction of 29.13%. These observations distinguish initial admission costs from subsequent usage on this synthetic workload.

All six cells finished in 402.323 seconds overall, with no error, timeout, replacement or campaign retry. Each cell used a fresh process and database, running sequentially in order AB/BA/AB on one Linux host. A is core `35dd711a…`, B is core `76dba2b1…`; the benchmark and data were shared. Active limits were observed: CPU quota 50%, memory limit 1 GiB, swap disabled, at most 64 tasks and no network. The cap was 180 seconds per child and 1,200 seconds for the unit. All children were waited for, the unit was inactive with PID zero, its cgroup empty or absent, and temporary RAM storage removed.

## Measured cycle

Each process first loaded 1,000 sources and synchronized the index. In the same memory instance, it added ten sources, read their exact references and complete contents, synchronized the index, and performed 50 searches with 50 explicit reads. The first ten searches each targeted a new source; the remaining 40 drew from the initial corpus using seed 20261021. The cycle then withdrew `note-1000`, checked the denied read and stale index, synchronized, checked that source's absence, and confirmed that `note-1001` remained retrievable and readable.

| Pair | Order | Cycle A → B | Reduction | B/A ratio | Cycle CPU A → B | Initial load A → B |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | AB | 19.497 → 18.973 s | 2.69% | 0.9731 | 9.726 → 9.465 s | 55.133 → 39.096 s |
| 2 | BA | 19.496 → 19.038 s | 2.35% | 0.9765 | 9.725 → 9.522 s | 55.280 → 39.172 s |
| 3 | AB | 19.300 → 18.977 s | 1.67% | 0.9833 | 9.630 → 9.460 s | 55.167 → 39.094 s |

Cycle elapsed time is the benchmark's marginal field, which excludes ingestion and the first synchronization. CPU is the sum of user and system deltas between the cycle's first and last sample boundaries. Its median paired reduction was **2.08%**, ranging from 1.76 to 2.68%, with a median difference of 0.203 CPU seconds. The median initial-load difference was 16.073 seconds, with reductions ranging from 29.09 to 29.14%. These percentages are not added to results from earlier studies.

## Phases and resources

The following values are medians of the three observations for each arm and phase. They do not reconstruct a single run. The JSON retains every cell's values, separate user and system CPU deltas, I/O, file sizes and RSS samples for every phase.

| Phase | Elapsed A → B | User+system CPU A → B |
| --- | ---: | ---: |
| Setup: ingestion | 55.000 → 38.909 s | 27.437 → 19.417 s |
| Setup: first synchronization | 0.184 → 0.195 s | 0.094 → 0.098 s |
| Cycle: ten admissions | 1.094 → 0.774 s | 0.552 → 0.383 s |
| Cycle: admission reads | 0.627 → 0.672 s | 0.331 → 0.331 s |
| Cycle: synchronization | 0.189 → 0.195 s | 0.098 → 0.100 s |
| Cycle: 50 searches and reads | 16.406 → 16.271 s | 8.189 → 8.108 s |
| Cycle: withdrawal and stale-index check | 0.208 → 0.208 s | 0.118 → 0.118 s |
| Cycle: synchronization after withdrawal | 0.188 → 0.198 s | 0.099 → 0.099 s |
| Cycle: final checks | 0.669 → 0.668 s | 0.328 → 0.327 s |

Sample boundaries and the benchmark's marginal timer have slightly different scopes. Both are retained in the JSON; their difference ranges from 0.002 to 0.011 seconds. This is not a measurement of total telemetry overhead. Every cell wrote 44 progress states. Checks, reads and telemetry writes contribute to observed time; no uninstrumented arm isolates their cost.

Sampled storage grew from **2,166,923 bytes after setup** to **2,293,899 bytes after the cycle**, an increase of 126,976 bytes in all six cells. File sizes are retained individually; equal sizes do not establish byte-identical databases. Data files were stored in RAM. For the cycle, `/proc/self/io` reported zero storage-layer read bytes and 73,728 write bytes, alongside 177,945,418 characters read, 45,100 read calls and 1,554 write calls. Characters written ranged from 3,120,386 to 3,120,455. These process counters also cover progress logs; their units are not interchangeable and do not establish an absence of physical I/O.

Final current RSS from `/proc/self/statm` ranged from 36,462,592 to 36,524,032 bytes. The separately retained `getrusage` peak ranged from 35,680,256 to 36,290,560 bytes. The two sources do not align in these observations; the JSON preserves both without replacing values or inferring memory savings. The reported peak covers the process lifetime, including setup. Size and RSS peaks between samples remain unknown.

## Correctness, provenance and scope

All six cells passed content and lifecycle checks, with 50 expected records, no missing or unexpected results, no truncation and 50 completed statuses. The query schedule, independently recomputed from synthetic sources before launch, retained SHA256 `43246effb8574adaeb53eb0dff4984a1b2845f7bd2acbe8b1c204bb678c57bfe`. Every cycle made ten puts, two synchronizations, 53 searches, 63 reads and one withdrawal: 129 explicit calls after setup's 1,001 calls. The 63 reads include two denials of the withdrawn source and the allowed control read. Searches used top_k 5 and a 200-character context budget.

Actual imported sources and their binding constants were observed for each process, with no bytecode caches present. All 36 files from the terminal collection matched their native receipt contents and hashes. Both arms used the same offline 0.3.0a2 support environment with three pinned modules per arm. Timings apply to that code and support environment, without attributing them to installed a4 distributions. The initial qualification failure, before ingestion, remains separately recorded; the corrected qualification passed before this single campaign. The JSON includes hashes for the prospective freeze, runner, both cores and observations.

Three pairs are descriptive observations. The 50 searches within a cell are not 50 independent replications; cold cache and load or order effects are not controlled. There was no minimum-gain requirement and no significance test is reported. This measurement does not establish general superiority, production latency, semantic quality, agent mission outcomes or power-loss durability. There were no provider calls, network downloads or production changes. Energy, billed charges and complete cost remain unknown.
