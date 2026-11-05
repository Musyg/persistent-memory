# Experience transfer with Hermès and ECC

[Français](README.fr.md)

**Campaign completed on November 5, 2026.** All 32 cases ran in four conditions, using the same model and up to three attempts on the new task. Hermès completed 10 of the 16 tasks where an earlier rule still applied, compared with 7 for the local ECC adaptation. When the new task specified a different rule, the results were 11 and 14 out of 16.

**The campaign did not establish the expected advantage under its predefined criteria.** The published evidence retains successes, failures, revisions and lesson-transfer records, including outcomes unfavorable to Hermès.

## Results

Each column covers the same cases in all four conditions.

| Condition | Earlier rule still applies, final result /16 | New rule, final result /16 | Correct first file /32 | Correct final file /32 |
| --- | ---: | ---: | ---: | ---: |
| H · Hermès memory | 10 | 11 | 6 | 21 |
| E · ECC adaptation | 7 | 14 | 5 | 21 |
| T · Task history | 9 | 14 | 4 | 23 |
| N · No history | 6 | 12 | 5 | 18 |

Both the first and final files are graded against the full task rule. The final counts show what the agent achieved within its revision budget. The change from first to final file describes that process; by itself, it does not isolate the causal effect of allowing revisions.

On the transfer cases, the Hermès–ECC difference is **+18.75 percentage points**. All three additional successes come from the stock task family: 7/8 versus 4/8. The admission family is tied at 3/8.

The predefined signal required an observed gain of at least 20 points and statistical evidence in both task families. A separate analysis assessed the non-degradation margin when the rule changes. Neither conclusion criterion was met. The joint directional test gives p = 1; the simultaneous 95% interval for the effect is −44.4 to +64.6 points. ECC completed three new-rule tasks that Hermès failed. The five-point non-degradation margin was not established. [Recalculable results](RESULT.json)

## From one task to the next

For each case, the agent completes six A tasks whose outcomes are checked. It then receives a B task with new inputs and must produce a CSV. The 16 transfer cases retain the threshold convention from the earlier tasks. In the other 16 cases, the new task explicitly states which convention to use. Each group contains eight admission cases and eight stock-management cases.

| Condition | Context added to the new task |
| --- | --- |
| H | Lessons that Hermès extracts, validates and retrieves. |
| E | Lessons ECC calls “instincts”, if it selects any for the new session. |
| T | A record of the six earlier tasks and their verified outcomes. |
| N | No history from the earlier tasks. |

All four conditions use the same quantized Qwen3-Coder-30B-A3B-Instruct and coding agent. The native workflow runs a planner, the Coder and a check, followed when needed by a reflector and a revision, with at most three Coder attempts. The evaluation therefore covers an agentic workflow with feedback.

The check available to the agent tests the format and the rows that both threshold conventions handle alike. An independent judge checks the full rule, including values equal to the threshold. Its expected answers are not shown to the agent. The final outcome is the primary measure. [Method and settings](METHOD.md)

The study compares the native Hermès integration with a local ECC adaptation. This public repository provides the reusable memory core and the public verification materials.

## Lesson transfer and evidence coverage

The complete extraction-to-consumption path is attested in 19 of the 32 Hermès cases. In the other 13, the normalizer retains an unknown extraction status: 12 A-task sources do not provide a literal result usable without executing the generated code, and one proposed lesson contradicts the convention demonstrated by its source. Validation rejects these inputs. This does not discard the B artifacts or their grades: all 128 task outcomes remain evaluated. The status alone does not establish a storage failure.

ECC has an attested path in all 32 cases: two pass a nonempty instinct context, while 30 have a known empty selection. A valid abstention counts as an observed path, without being reported as successful experience transfer. Task history is available in all 32 T cases.

These records distinguish the quality of the deliverable from evidence that the system extracted and passed on a lesson. [Per-condition data](ARMS.json) · [Data format](FORMAT.md)

## Resources

The campaign comprises 544 phases and **1,016 local generations**, with **1,002,470 charged input tokens and 125,865 charged output tokens**. Its 3,916 instrumented HTTP operations cover request preparation and server checks. They are not a count of the agent’s task-level tool use.

No paid generation API was called. Hardware and energy costs were not priced. The A tasks, shared across all four conditions, are counted once in the campaign total. Per-condition accounting separates that common preparation from each condition’s learning and task-completion costs. [Resource details](RESULT.json) · [Accounting rules](FORMAT.md)

The table below includes each condition’s own learning and B tasks. The six A tasks per case form a common preparation stage: 384 generations, 155,049 input tokens and 37,063 output tokens across the campaign.

| Condition | Generations | Input tokens | Output tokens | Sum of model-call durations |
| --- | ---: | ---: | ---: | ---: |
| H | 234 | 221,411 | 38,444 | 179.0 s |
| E | 146 | 278,289 | 15,291 | 93.2 s |
| T | 131 | 273,344 | 19,539 | 115.9 s |
| N | 121 | 74,377 | 15,528 | 72.0 s |

Durations sum the observed calls. They measure neither GPU compute time alone nor the full benchmark runtime, which also includes startup, checks, port waits and archiving. Hermès uses fewer input tokens than ECC in this setup, but more generations, output tokens and call time. The measurements therefore do not establish an overall efficiency advantage.

## Verify the results

The public files contain synthetic cases and outputs approved for release after review. Private memory data, operational identifiers, secrets, production logs and private backups are excluded.

From this directory, with Python 3.11 or later:

```sh
python -I -B verify.py
python -I -B REGRADING/verify_regrading.py
```

The first command recalculates the aggregates and statistical criteria from the 32 cases and 128 published rows. The second regrades the available synthetic artifacts with the typed oracle, without executing model-generated code. [Verification appendix](REGRADING/README.md)

The criteria, corpus and settings were fixed before confirmation. Earlier development trials and the qualification run below do not enter its scores. Collection incidents were reconciled without replaying generation phases. The historical [12/12 functional result](../../MEMORY-COMPARISON.md) retains the scope of its original evaluation.

## Earlier qualification run, outside the score

A previously used synthetic case required 39 generations with the corrected workflow. Hermès stored four validated lessons, and its reader passed three to the planner and Coder. The ECC observer analyzed the 24 A-task events in 0.806 seconds and returned a valid empty list.

| Condition | First check available to the agent | Final task outcome | Coder attempts |
| --- | --- | --- | ---: |
| H | Failed | Passed | 2 |
| E | Failed | Failed | 3 |
| T | Failed | Passed | 2 |
| N | Failed | Failed | 3 |

This qualification run checks that revisions work and that stored lessons reach the agent. It is excluded from the confirmatory result. Its initial format check differs from the full-rule grade of the first file shown above. [Qualification run data](witness-summary.json)

## ECC provenance

Arm E uses **ECC Continuous Learning v2.1**, from the project by Affaan Mustafa and its contributors, pinned to commit `b38be6a7f6350964d59328b52f0624e1d1d552d1`. The upstream manifest lists `ecc-universal` 2.2.3 under the MIT license. The benchmark runs the pinned observation and session-start hooks, adapting observer analysis to a local JSON call with Qwen3-Coder. The findings apply to that adaptation, these two task families and this budget.

[Pinned source](https://github.com/affaan-m/ECC/tree/b38be6a7f6350964d59328b52f0624e1d1d552d1) · [Skill documentation](https://github.com/affaan-m/ECC/blob/b38be6a7f6350964d59328b52f0624e1d1d552d1/skills/continuous-learning-v2/SKILL.md) · [MIT license](https://github.com/affaan-m/ECC/blob/b38be6a7f6350964d59328b52f0624e1d1d552d1/LICENSE)
