# Generate new answers with the public component

This optional directory reuses the four qualified generation modules, byte for byte. It does not contain a new runner, HTTP client, budget ledger or fleet dependency. Source pins are in `SOURCE-PROVENANCE.json`. This copy passed the five existing Linux checks with the pinned public package runtime, including six simulated requests and rejection of both inactive budgets before credential access. `NATIVE-QUALIFICATION.json` records the dependency versions and scope of that verification.

The study's recorded answers are recalculated offline using the parent archive's reporting command. The command below instead makes **new, paid, stochastic requests**. It does not replace recorded answers or reproduce them bit for bit. Models can change behind their aliases; requested and returned model IDs are recorded and checked.

## Prepare a small selection

Use Linux, the qualified Python 3.12 runtime, `httpx` and the verified public `hermes-memory-core==0.3.0a2` distribution. Install the public project in a separate virtual environment, for example `python3 -m pip install /path/to/verified/persistent-memory httpx`. The final native qualification must record the exact dependency versions. No private Hermes module, tokenizer, orchestrator, SSH configuration or original Root grant is needed. Keep this directory free of unrelated Python modules.

Verify the published archive's `SHA256SUMS` before using it. Follow [CONFIGURATION.md](CONFIGURATION.md) to transform **one** block from the non-executable public generation-plan projection into an inactive local profile/budget and an input packet containing only that block's cases. The same task, query, documents and cells are retained; the packet gets its own SHA256. No oracle, metadata labels or judge output is opened by that transformation.

`DEV/` contains the existing four disposable synthetic development fixtures, not the 500-task campaign. Each example profile selects only the first development case in three arms: typed memory, no memory and the existing lexical baseline. The inactive budgets reserve at most three calls per model and **cannot send** as supplied. Development results must remain labelled development-only.

## Authorize a bounded attempt

The frozen generation contract accepts profiles `volume_luna6_none_v1` (`gpt-6-luna`, reasoning `none`) and `volume_sol61_low_v1` (`gpt-6.1-sol`, reasoning `low`). Both use the same evidence retrieval, prompt and text-only API. Limits are 1–3 selected calls, a 300-second run, 90 seconds per request, 10,240 complete-request UTF-8 bytes plus 1,024 framing tokens, at most 11,264 input tokens and 2,048 output tokens. Temperature is omitted. There is no automatic retry or substitute model.

At the campaign's frozen rates, the worst reservation per generation is USD `0.0021504` for Luna or `0.043008` for Sol; the three-call examples total `0.0064512` or `0.129024`. These are historical rate-contract bounds, **not verification of today's prices or account billing**. Before enabling a budget, its operator must verify current pricing and the qualified byte/token/reasoning bounds. If the fixed contract no longer bounds the cost, stop and use a separately qualified version; do not bypass the validation or change the fixed limits.

After that review, copy the selected `*-budget.INACTIVE.json` to `budget.json`; set only `authorized_for_execution`, `price_verified`, `tokenizer_bound_verified`, `reasoning_total_bound_verified` to `true` and `expires_at_epoch` to a finite future Unix timestamp. Keep every profile, cell, price and request option unchanged. Freeze the resulting bytes with `sha256sum budget.json`. This authorization belongs to the new operator, not the historical campaign.

Save your own API key in a regular file owned by the current user, mode `0600`; never include it in the archive or shell history. From this directory, after preparing `work/profile.json`, `work/inputs.json` and `work/budget.json`:

```sh
PYTHONPATH="$PWD/CODE" python3 -P -B CODE/run_pilot.py \
  --consumer public_portable \
  --inputs "$PWD/work/inputs.json" \
  --dataset-sha256 "$(sha256sum work/inputs.json | cut -d ' ' -f1)" \
  --profile "$PWD/work/profile.json" \
  --budget "$PWD/work/budget.json" \
  --budget-sha256 "$(sha256sum work/budget.json | cut -d ' ' -f1)" \
  --api-key-file "$HOME/.config/memory-replay/openai.key" \
  --output "$PWD/work/new-attempt"
```

Only `CODE/` is added to the import path; `-P` prevents implicit working-directory imports. The output path and its adjacent `new-attempt-budget.sqlite` must not exist. Do not remove a ledger to repeat an attempt after an uncertain send. The existing provider makes a durable worst-case reservation before a single send per cell; incomplete or failed calls retain their trace/reservation and are not silently retried. Read the report's individual statuses; the CLI summary is not a quality score.

The run records `report.json`, request/response traces, attempts and authority/revocation checks. Raw local traces can contain provider response identifiers and paths: they are **not approved public export files**. Keep the new outputs separate from the published study. Publish only through the existing reviewed normalization/export pipeline. Fresh memory is created per case, policy and repetition; the query comes from the fixture, not an evaluated autonomous planner.
