# Persistent memory — validation results

100 selected tasks, 100 scenario groups, three repetitions and 1,500 planned episodes. Tasks within a group are not independent.

| Measure | Result |
|---|---|
| Answers delivered | 1500 / 1500 |
| Episodes not executed | 0 |
| Complete execution confirmed | yes |
| Confirmed critical incidents | 0 |
| A success, conservative bounds | 99.33 % / 99.33 % |
| A−B effect, nominal 95% uncertainty interval | 89.00 % / 90.00 % |
| Absolute quality requirement met | yes |
| Differential benefit confirmed | yes |
| Execution, safety and delivery requirements met | yes |

The calculation retains unknown outcomes and every planned episode. The paired bootstrap resamples scenario groups within each family (10,000 draws); repetitions do not become independent tasks.

## Secondary comparisons

- gpt-6-luna, memory_on − simple_baseline: 100 tasks from the frozen subset; 95 %: -0.33 % / 3.33 %; seed 20261025.
- gpt-6.1-sol, memory_on − memory_off: 100 tasks from the frozen subset; 95 %: 90.00 % / 90.00 %; seed 20261026.

## Stability and first repetition

`pass^3` requires three confirmed successes; unknown outcomes remain visible. Counts below are task counts.

| Modèle / bras | 3/3 | Failure | Unknown |
|---|---:|---:|---:|
| gpt-6-luna/memory_off | 9 | 91 | 0 |
| gpt-6-luna/memory_on | 99 | 1 | 0 |
| gpt-6-luna/simple_baseline | 96 | 4 | 0 |
| gpt-6.1-sol/memory_off | 10 | 90 | 0 |
| gpt-6.1-sol/memory_on | 100 | 0 | 0 |

First A/B repetition: gain=90, loss=0, tie_success=10, tie_failure=0, unknown=0.

## Emissions and non-delivery

| Phase | Confirmed emissions | Unknown emission | Confirmed not emitted | Not executed |
|---|---:|---:|---:|---:|
| generation | 1500 | 0 | 0 | 0 |
| judges | 3000 | 0 | 0 | 0 |

An uncertain emission retains that status and its financial exposure; it is not counted as zero emissions. Episodes not executed are a subset, not an additional column to sum.

| Modèle / bras | Tasks / groups | Non-delivery | One-sided95% upper bound |
|---|---:|---:|---:|
| gpt-6-luna / memory_off | 100 / 100 | 0.000 % | 0.000 % |
| gpt-6-luna / memory_on | 100 / 100 | 0.000 % | 0.000 % |
| gpt-6-luna / simple_baseline | 100 / 100 | 0.000 % | 0.000 % |
| gpt-6.1-sol / memory_off | 100 / 100 | 0.000 % | 0.000 % |
| gpt-6.1-sol / memory_on | 100 / 100 | 0.000 % | 0.000 % |

Bounds use the frozen grouped bootstrap, 10,000 draws and seed20261024, keeping all three repetitions together. Descriptive first-repetition Wilson bounds remain separate in the JSON.

## Families — exploratory results

| Family | Tasks | Effect bounds |
|---|---:|---|
| F01 | 10 | 100.00 % / 100.00 % |
| F02 | 10 | 100.00 % / 100.00 % |
| F03 | 10 | 100.00 % / 100.00 % |
| F04 | 10 | 100.00 % / 100.00 % |
| F05 | 10 | 100.00 % / 100.00 % |
| F06 | 10 | 100.00 % / 100.00 % |
| F07 | 10 | 100.00 % / 100.00 % |
| F08 | 10 | 100.00 % / 100.00 % |
| F09 | 10 | -3.33 % / -3.33 % |
| F10 | 10 | 100.00 % / 100.00 % |

## Observed latency

| Modèle / bras | N | p50 (s) | p95 (s) |
|---|---:|---:|---:|
| gpt-6-luna / memory_off | 300 | 1.301 | 1.963 |
| gpt-6-luna / memory_on | 300 | 1.449 | 2.514 |
| gpt-6-luna / simple_baseline | 300 | 1.470 | 2.460 |
| gpt-6.1-sol / memory_off | 300 | 2.312 | 3.339 |
| gpt-6.1-sol / memory_on | 300 | 2.517 | 3.690 |

Total consumer time for completed answers with timing data, including preparation, retrieval and checks. Missing timings are not replaced with zero.

## Costs and scope

Generation cap: 27.74016 USD; judge cap: 41.9328 USD.
Reconciled conservative debit: 212.0767488 USD; cost calculated from reported usage: unknown; invoice: unknown.

Two AI judges, no human audit; their errors may be correlated. The technical test at 5,000 sources reached its 40-minute limit: that load is not qualified. Results cover the public component and the exercised portable consumer, without certifying the entire Hermes production system.

Episode IDs, individual outcomes, source references and SHA256 pins are available in REPORT.json and MANIFEST.json.
