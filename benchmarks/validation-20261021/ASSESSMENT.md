# Historical campaign assessment and evaluator erratum

The campaign closed on 21–22 October 2026. Its original answers, judgments, scores, unknown outcomes and thresholds are preserved. **It did not meet the absolute quality requirement.** This archive supports inspection and exact recalculation of an automated study; it does not certify calibrated business quality or all Hermes production workloads.

## Recorded result

The principal memory arm has 1,290 confirmed successes, 76 confirmed failures and 134 unknowns across 1,500 generation episodes: a conservative success rate of **86.00%** and a descriptive upper bound of **94.93%**. Its one-sided nominal 95% lower bound is **83.67%**. Both absolute requirements fail: 86.00% < 90%, and 83.67% < 85%. Unknowns have not been converted to successes.

Under the original automated protocol, the conservative nominal 95% interval for the paired memory-minus-no-memory effect is **+61.00 to +77.33 percentage points**. The second generation model, on the fixed 100-task subset, gives **+56.67 to +77.33 points**. Against lexical retrieval, **−2.67 to +26.67 points** crosses zero: superiority is not established. These intervals do not account for evaluator bias.

There are 500 synthetic tasks arranged in **100 scenario groups**, not 500 independent worlds. Three repetitions stay together in the group-stratified bootstrap. All 3,900 generation episodes completed. Across 3,900 judge pairs, 223 disagree and three have a missing or invalid judgment. The 226 unknown outcomes (5.79%) do not identify memory failures: they can reflect answer errors, evaluator errors, ambiguity or an unavailable verdict. No critical violation was confirmed by the original judges; that observation is not a universal safety guarantee.

## Demonstrated evaluator defect

The original judge prompt included the question, answer, a shortened oracle and available evidence IDs, **without the evidence texts supplied to the answer model**. A supported addition absent from the shortened oracle could therefore be treated as invented. Direct comparisons demonstrate three such penalties:

| Public episode ID | Detail rejected by a judge | Evidence actually supplied |
|---|---|---|
| `V21-L-F04-G04-T04-R1-ON` | Thursday delivery | `F04-G04-D03` explicitly schedules delivery to Hall Three on Thursday. |
| `V21-L-F05-G01-T01-R2-ON` | Test socket, Mila’s hours and another staff member | `F05-G01-D02` supplies all three details. |
| `V21-L-F08-G01-T04-R3-ON` | The fault diagnosis had not arrived | `F08-G01-D01` explicitly says the diagnosis has not yet been received. |

These examples establish a defect, not its frequency across the whole study. They do not justify changing historical unknowns into passes or deriving a corrected success rate. The two incomplete judge JSON bodies and the one timeout also remain unchanged.

## Genuine answer errors also remain

- `V21-L-F04-G06-T03-R2-ON` has 90 crowns for ten weeks available but does not infer nine crowns per week and calls the price unknown.
- `V21-L-F09-G06-T03-R1-ON` accepts a rota with one person after noon although two are required throughout.
- `V21-L-F10-G01-T03-R2-ON` fails to attach the available budget to the current workspace and calls “our” budget unknown.

The available facts are not reliably used in these answers. This observation does not by itself locate the cause in storage, retrieval or generation. The examples are descriptive, not an estimate of the prevalence of each cause.

## Interpretation and reproducibility

The positive contrast against no memory is conditional on this corpus and the original, imperfect automated evaluation. It is not a calibrated estimate of business quality. The study has **no external human quality audit**; both judges are AI models and their errors may be correlated. Its local pre-call freeze is documented, but publication after measurement is not an externally timestamped preregistration.

Exact offline recalculation reproduces those historical results; it does not repair their evaluator. A future validation would need qualified judges that receive the exact delivered evidence texts, audited question/oracle coverage, and a fresh cohort frozen before model calls. Such a corrected validation is **not a result of this archive**. No old score, response or oracle has been overwritten.

[Execution and cost accounting](EXECUTION.json) separates the frozen study from a distinct eight-call operational replay. Conservative maximum exposure, known usage estimates and actual billing are different quantities.
