# From an observed outcome to a reusable lesson

23 October 2026 · [Français](README.fr.md) · [Results](RESULT.json) · [Compressed observations](OBSERVATIONS.json.gz) · [Episode plan](PLAN.json)

In this synthetic study, a model performed task A, received feedback on its actual output, extracted a lesson and then attempted a different task B. A derived lesson improved the observed B success count over no experience for both models. Against the complete A trace and feedback, it added nine successful tasks for Luna and matched the complete trace for Sol.

## Verified B outcomes

Each row contains 24 B tasks. All 192 B outcomes are known; success requires the expected business file and a valid completion control, checked by a separate process that reopens the actual files. Input tokens cover the complete B prompt, not a separately tokenized memory context.

| Model | Experience arm | Successful B tasks | B input tokens |
| --- | --- | ---: | ---: |
| GPT-6 Luna | Derived lesson | 22/24 | 22,718 |
| GPT-6 Luna | Complete trace + feedback | 13/24 | 57,194 |
| GPT-6 Luna | No experience | 7/24 | 16,532 |
| GPT-6 Luna | Lesson withdrawn | 7/24 | 16,565 |
| GPT-6.1 Sol | Derived lesson | 24/24 | 23,310 |
| GPT-6.1 Sol | Complete trace + feedback | 24/24 | 57,324 |
| GPT-6.1 Sol | No experience | 12/24 | 16,536 |
| GPT-6.1 Sol | Lesson withdrawn | 10/24 | 16,557 |

For Luna, the derived lesson adds 15 successes over no experience and nine over the raw trace. For Sol, it adds 12 over no experience and matches the raw trace. These are descriptive paired differences on this suite. They do not establish a universal advantage, statistical significance or superiority at equal expenditure.

## What was learned and transferred

The six task families cover identifier handling, threshold boundaries, debit/credit signs, revision conflicts, CSV encoding and approval flags. Each has a French and an English instance. Task A exposes a receiver convention through an actual artifact and business feedback; B changes the goal and data while retaining that convention. For example, feedback about how the receiver handles an exact threshold in A can inform which rows belong in a different B report.

A succeeded in 24 of 48 episodes. All 48 feedback records were discriminating, including those following a wrong A outcome. Extraction used only the actual A trace and that feedback, before B was executed. The extractor produced 48 well-formed candidates and selected the correct structured convention in all 48. The free-text explanation was not semantically annotated; these scores do not establish that every sentence in a lesson is correct.

Each candidate was stored through `Memory.derive` with dependencies on the actual A trace and feedback, without promotion to an active policy. The raw arm received the same complete input as the extractor, including A's prompt, response, observed effects and feedback. It was not replaced with a summary. All four B arms had the same business permissions and task data. The withdrawn arm revoked a parent of the stored experience, testing its exclusion from reuse; it remained allowed to perform B without that experience. Withdrawal is a safety control, outside the two primary comparisons.

The study contains **48 paired episodes**: six families × two languages × two models × two repetitions. Each episode has one A call, one extraction and four B calls, for **288 actual model calls**. Repetitions and arms share the same episode context. They are not 288 independent business tasks. The B arm order was fixed as raw → derived → none → withdrawn, with three episodes running concurrently; the timings are not an independent latency comparison. There were no retries, replacement cases or outcome-based exclusions. No confidence interval, p-value or bootstrap is reported.

## Did the receiver mistake recur?

The existing Registry independently reopened and verified the files produced by all 192 B tasks across 16 partitions, preserving **119 successes, 73 failures and no unknown quality outcomes**. The 7,424 original study files remained unchanged. The [Registry projection](REGISTRY.json) retains the verification counts and provenance.

Recurrence is a narrower diagnostic: after A used the wrong receiver convention, did the actual B artifact repeat that convention? There are **24 eligible episodes per arm**, comprising 11 Luna and 13 Sol episodes. The complete quality results above still cover all 48 B tasks per arm across both models.

| Experience arm | Eligible episodes | Repeated receiver error | Correct receiver convention in B | Unknown cause |
| --- | ---: | ---: | ---: | ---: |
| Derived lesson | 24 | 0 | 24 | 0 |
| Complete trace + feedback | 24 | 2 | 18 | 4 |
| No experience | 24 | 17 | 5 | 2 |
| Lesson withdrawn | 24 | 13 | 6 | 5 |

If a B artifact matches neither of the two conventions defined by the protocol, the cause of the error remains unknown. A generic task failure is not automatically counted as recurrence, and a correct receiver convention does not by itself satisfy every file/control requirement. This diagnostic therefore remains separate from full B success.

## Context and cost

The experience path allows 8,000 characters and five items, under the unchanged 10,240-byte complete-request cap. The [prospective cap decision](CAP-DECISION.md) and [lossless prompt representation](PROMPT-REPRESENTATION.md) were fixed after checks using simulated responses and before model calls. Earlier studies retain their original prompts and limits. Common caps do not imply equal realized tokens or spend.

Sol matched raw-trace quality with fewer B input tokens when using the derived lesson. Producing that lesson also required an extraction call. A raw-history deployment would not require this step, so B-only counts do not establish an end-to-end token saving. The construction work is retained separately:

| Phase, both models | Calls | Input tokens | Output tokens |
| --- | ---: | ---: | ---: |
| A and its observed outcome | 48 | 28,327 | 3,525 |
| Lesson extraction | 48 | 88,609 | 8,797 |
| All four B arms | 192 | 226,736 | 24,012 |

Reported usage totals 380,006 tokens across all 288 calls. The historical generation estimate is **USD 0.2639163 for 187 calls only**. The remaining 101 include cache-write usage that this frozen calculator does not price; the reported cache-write count is 208,158 tokens. Their cost remains unknown. In particular, extraction has no priced coverage here and must not be treated as free. The invoice, complete cost of memory construction and operation, and an equal-spend comparison remain unavailable.

## Reproduction

The [protocol](PROTOCOL.md), plan and observations retain the actual frozen study. With both packages installed, the offline calculation uses the standard-library `gzip` module to read `OBSERVATIONS.json.gz`, then passes the decoded observations and exact `PLAN.json` bytes to `calculate_experience` in the existing [benchmark module](../../run_benchmark.py). It makes no new provider calls. Detailed scores and coverage remain in `RESULT.json`.
