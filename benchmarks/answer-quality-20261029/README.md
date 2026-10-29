# Persistent memory: comparison across eight histories

Across eight synthetic development histories, the memory configuration achieves **77 successes out of 96**, compared with **29 out of 96** for a versioned lexical baseline with validity checks. The evaluated component is Persistent Memory's portable core. Four French and four English histories share one scenario family. Replication on an independent test set remains future work.

| Primary outcome | Memory | Lexical baseline |
| --- | ---: | ---: |
| Success | 77 | 29 |
| Failure | 10 | 58 |
| Unknown | 9 | 9 |

The 96 paired comparisons yield 45 gains, no observed losses, 26 shared successes, 10 shared failures and 15 unknown pairs. Every attempt remains in the denominator. Two blinded Codex readers made 382 judgments on the 191 available artifacts and agreed on success. Generation used one model, gpt-6-luna.

Collection recorded 192 actual HTTP calls, with no retries, and 191 artifact readbacks. Seventeen incorrect control identifiers and one invalid JSON response receive no primary success credit. A separate post hoc assessment of artifact content gives 85/96 and 31/96 successes; the missing artifact remains unknown.

Memory supplies every required fact for 79 of the 88 questions with required facts, versus 22/88 for the baseline, covering 111/120 facts versus 39/120. Supplied text and metadata match the expected valid versions. This coverage offers a plausible account of the benefit without establishing why each answer succeeded or failed. An isolated follow-up replay exactly reproduces the nine affected packets: eligible schedule facts rank 10 to 52, below the selection cutoff of five items.

Reported usage gives a generation estimate of **USD 0.038438475**, using the `default` tier and 228,347 cache write tokens. Per primary success, the estimates are USD 0.000250514 with memory and USD 0.000660308 for the baseline. The invoice and full agency cost are unknown.

[EVIDENCE192.json](EVIDENCE192.json) contains the facts, controls, original texts and verdicts for all 192 cases. With Python 3, `python verify_pilot.py` recalculates the results and tariff estimate while checking their hashes. [RESULTS.json](RESULTS.json) records the dated rates and official pricing sources.
