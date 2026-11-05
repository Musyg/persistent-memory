# Offline verification of the agentic memory comparison

[Français](FORMAT.fr.md)

The confirmation study assigns four conditions to each of 32 synthetic worlds. H uses Hermes, E uses ECC CL v2 with a local adapter, T receives the authorized trace, and N receives no prior experience. The world is the paired unit. Two fixed generators each contribute eight positive and eight negative worlds. W and DEV remain separate.

## Files and identifiers

- `ROSTER.json` uses `persistent-memory.conf-roster.v1` and has a `worlds` array with exactly 32 rows. Each row contains `world` (`W01` through `W32`), `cohort` (`positive` or `negative`), `stratum` (`admission` or `stock`), `case_join_sha256` and `shared_A` resources. The operator keeps the checked correspondence with the sealed roster separately.
- `case_join_sha256` hashes the sorted, compact ASCII JSON object with keys `schema`, `world`, `cohort` and `stratum`. Its schema value is `persistent-memory.conf-public-join.v1`. This hash identifies the public projection. It does not identify a request or authenticate the original private receipt. `verify.py` supplies it to the existing reducer's request-identity field.
- `ARMS.json` uses `persistent-memory.conf-arms.v1` and has a `rows` array with exactly 128 world/arm rows. The allowlist in `verify.py` is the schema. It includes the independent gate, terminal and pipeline statuses, terminal business verdict, first-attempt verdict, Coder attempt count, experience observation, Y/Z and resource counts. Use `null` for an unobserved measurement. Unrun rows remain assigned and unresolved. Use only the enumerated reason codes, with no free-form logs or errors.
- `RESULT.json` contains the pinned reduction and descriptive totals. `MANIFEST.json` uses `persistent-memory.conf-public-manifest.v1`. Its `files` object maps `ROSTER.json`, `ARMS.json`, `RESULT.json`, `verify.py`, `reduce_conf_grades.py` and `comparative_statistics.py` to SHA-256 hashes.

## Measurements

Common A resources appear once per world. An arm's resource row covers its own operations, including LE presentations for H and the ECC phase for E. The trace projection shares that phase and makes no additional model call. Each model operation is counted in its own unit. Phase launches, reserved generations, actual generation requests on the wire, and instrumented model tools are separate. Model latency is the sum of observed call durations in milliseconds. Report charged and observed tokens separately, with coverage for each total. These figures measure resource use. They do not estimate power use or infrastructure cost.

Y measures terminal business success under valid rights and integrity. Z measures whether all applicable stages and the terminal grade were observed and complete. A known empty experience context can accompany either a correct or an incorrect answer. `OBSERVED_CONTEXT` records that the assigned context reached B. In T it is the trace. In H or E it can include a lesson, without establishing its causal contribution to the outcome.

The existing reducer preserves all assigned rows and reports unresolved evidence and sensitivity bounds. The primary comparison is H versus E on positive worlds, using the registered exact directional test across both strata and the simultaneous 95% effect interval. The negative cohort measures relative harm separately. The progression signal requires a useful point estimate of at least 20 percentage points, directional significance and zero critical violations. It does not establish a lower effect bound of 20 points or broad superiority. An incomplete grid blocks the confirmatory inference. The statistics describe these two fixed generators.

## Verification and scope

From this directory, run `python -I -B verify.py`. It checks the file manifest and reuses the original reducer and statistics module. To generate the summary for review before sealing, run `python -I -B verify.py --calculate`. This is an offline recalculation of the published grades and resource totals. It does not replay a model, verify private operational receipts or independently grade an unpublished artifact.

After confirmation closes, a separate regrading appendix may disclose the synthetic B inputs, expected columns and rows, and the first and terminal model responses that pass a disclosure review. The existing `coder_record` checks the two-field response shape and the existing `business_b_oracle` uses `literal_result` to inspect the single `RESULT` assignment without executing generated code. These exact functions can be reused without Hermes. Publishing the exact safe synthetic identifiers and bytes preserves the original grading semantics. A redacted response, missing response or altered fixture must be identified separately. The appendix must not treat a reconstructed response as the original or count an unavailable artifact as a verified grade. Never publish model requests, memory, private traces, host paths or keys.
