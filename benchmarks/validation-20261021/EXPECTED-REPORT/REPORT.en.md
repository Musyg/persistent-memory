# Persistent memory — validation results

500 selected tasks, 100 scenario groups, three repetitions and 3,900 planned episodes. Tasks within a group are not independent.

| Measure | Result |
|---|---|
| Answers delivered | 3900 / 3900 |
| Episodes not executed | 0 |
| Complete execution confirmed | yes |
| Confirmed critical incidents | 0 |
| A success, conservative bounds | 86.00 % / 94.93 % |
| A−B effect, nominal 95% uncertainty interval | 61.00 % / 77.33 % |
| Absolute quality requirement met | no |
| Differential benefit confirmed | yes |
| Execution, safety and delivery requirements met | yes |

The calculation retains unknown outcomes and every planned episode. The paired bootstrap resamples scenario groups within each family (10,000 draws); repetitions do not become independent tasks.

## Secondary comparisons

- gpt-6-luna, memory_on − simple_baseline: 100 tasks from the frozen subset; 95 %: -2.67 % / 26.67 %; seed 20261025.
- gpt-6.1-sol, memory_on − memory_off: 100 tasks from the frozen subset; 95 %: 56.67 % / 77.33 %; seed 20261026.

## Stability and first repetition

`pass^3` requires three confirmed successes; unknown outcomes remain visible. Counts below are task counts.

| Modèle / bras | 3/3 | Failure | Unknown |
|---|---:|---:|---:|
| gpt-6-luna/memory_off | 87 | 398 | 15 |
| gpt-6-luna/memory_on | 383 | 42 | 75 |
| gpt-6-luna/simple_baseline | 64 | 22 | 14 |
| gpt-6.1-sol/memory_off | 20 | 76 | 4 |
| gpt-6.1-sol/memory_on | 81 | 9 | 10 |

First A/B repetition: gain=327, loss=0, tie_success=91, tie_failure=21, unknown=61.

## Emissions and non-delivery

| Phase | Confirmed emissions | Unknown emission | Confirmed not emitted | Not executed |
|---|---:|---:|---:|---:|
| generation | 3900 | 0 | 0 | 0 |
| judges | 7800 | 0 | 0 | 0 |

An uncertain emission retains that status and its financial exposure; it is not counted as zero emissions. Episodes not executed are a subset, not an additional column to sum.

| Modèle / bras | Tasks / groups | Non-delivery | One-sided95% upper bound |
|---|---:|---:|---:|
| gpt-6-luna / memory_off | 500 / 100 | 0.000 % | 0.000 % |
| gpt-6-luna / memory_on | 500 / 100 | 0.000 % | 0.000 % |
| gpt-6-luna / simple_baseline | 100 / 100 | 0.000 % | 0.000 % |
| gpt-6.1-sol / memory_off | 100 / 100 | 0.000 % | 0.000 % |
| gpt-6.1-sol / memory_on | 100 / 100 | 0.000 % | 0.000 % |

Bounds use the frozen grouped bootstrap, 10,000 draws and seed20261024, keeping all three repetitions together. Descriptive first-repetition Wilson bounds remain separate in the JSON.

## Families — exploratory results

| Family | Tasks | Effect bounds |
|---|---:|---|
| F01 | 50 | 92.00 % / 96.00 % |
| F02 | 50 | 68.00 % / 87.33 % |
| F03 | 50 | 88.67 % / 96.67 % |
| F04 | 50 | 94.00 % / 99.33 % |
| F05 | 50 | 75.33 % / 87.33 % |
| F06 | 50 | 73.33 % / 87.33 % |
| F07 | 50 | 82.00 % / 93.33 % |
| F08 | 50 | 12.00 % / 36.00 % |
| F09 | 50 | -7.33 % / 6.67 % |
| F10 | 50 | 59.33 % / 64.67 % |

## Observed latency

| Modèle / bras | N | p50 (s) | p95 (s) |
|---|---:|---:|---:|
| gpt-6-luna / memory_off | 1500 | 1.356 | 2.163 |
| gpt-6-luna / memory_on | 1500 | 1.554 | 3.019 |
| gpt-6-luna / simple_baseline | 300 | 1.551 | 2.533 |
| gpt-6.1-sol / memory_off | 300 | 2.591 | 4.183 |
| gpt-6.1-sol / memory_on | 300 | 2.842 | 5.750 |

Total consumer time for completed answers with timing data, including preparation, retrieval and checks. Missing timings are not replaced with zero.

## Costs and scope

Generation cap: 32.90112 USD; judge cap: 109.02528 USD.
Reconciled conservative debit: 141.9995136 USD; cost calculated from reported usage: unknown; invoice: unknown.

Two AI judges, no human audit; their errors may be correlated. The technical test at 5,000 sources reached its 40-minute limit: that load is not qualified. Results cover the public component and the exercised portable consumer, without certifying the entire Hermes production system.

Episode IDs, individual outcomes, source references and SHA256 pins are available in REPORT.json and MANIFEST.json.
