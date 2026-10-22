# Persistent memory: reproducible validation data

This is the historical archive of the campaign closed on 21–22 October 2026. Absolute quality was **not qualified**: the conservative success rate was **86.00%**, with a one-sided 95% lower bound of **83.67%**, below the required 90% / 85%. The original judges received evidence IDs but not the evidence texts, and demonstrably penalized supported details. These are historical automated results conditional on that evaluator, not calibrated business-quality measurements. Read the [assessment and evaluator erratum](ASSESSMENT.md) alongside the unchanged figures in `EXPECTED-REPORT/REPORT.en.md` and `REPORT.fr.md`.

The study plan covers 500 selected synthetic tasks, 100 scenario groups, three repetitions, and 3,900 generation episodes. The principal comparison uses the public typed-memory component versus no memory on 500 tasks. The frozen 100-task subset adds the existing lexical comparator and confirmation on a second generation model. Two AI judges evaluate eligible answers; their errors may be correlated, and this is not an independent human quality audit or a guarantee for every production workload.

The protocol and oracles were frozen locally before the calls. Hashes and receipts document that internal chain; publication on GitHub happens after measurement and is not an externally timestamped preregistration. Each case, policy and repetition uses fresh memory and a fixture-supplied query. The 500 tasks evaluate this retrieval-and-answer path; they do not evaluate an autonomous planner or one memory accumulating 500 sessions.

## Recalculate offline

Use Linux and Python 3.12, the qualified runtime version. Report computation uses only the Python standard library: no account, API key, paid model, private Hermes service, database, or network request is required.

From this directory:

```sh
sha256sum -c SHA256SUMS
python3 -P -B CODE/report.py \
  --manifest REPORTING-INPUTS.json \
  --manifest-sha256 "$(cat REPORTING-INPUTS.sha256)" \
  --output ../memory-report-recalculated
diff -u EXPECTED-REPORT/REPORT.en.md ../memory-report-recalculated/REPORT.en.md
diff -u EXPECTED-REPORT/REPORT.fr.md ../memory-report-recalculated/REPORT.fr.md
diff -u EXPECTED-REPORT/REPORT.json ../memory-report-recalculated/REPORT.json
```

Use a new output directory for every calculation. `CODE/report.py` and `CODE/volume_analysis.py` are exact copies of the qualified implementations. They retain all planned episodes, unknown outcomes, the paired scenario-group bootstrap, the frozen seeds, `pass^3`, secondary comparisons, delivery bounds and separate evidence gates. A missing or uncertain attempt is not silently converted into success, failure, zero emissions or zero spending. Costs inferred from usage and an actual invoice remain distinct.

The reported criteria are explicit: confirmed execution, no observed confirmed critical violation, operational non-delivery at most 1%, principal success at least 90% with its one-sided 95% lower bound at least 85%, and a positive lower 95% bound on the paired effect for a benefit claim. These are the study's engineering requirements, not a universal certification standard. The task repetitions are not counted as independent tasks.

## What is preserved

`DATA/CASES.json`, `ORACLE.json`, `METADATA.json` and `SUBSET.json` retain their original synthetic bytes. The oracle and case hashes match the original commitments. Generation bodies, evidence, judge bodies, statuses, unknowns, model identities, usage and measured durations are preserved in the normalized files. No failed answer is rewritten to obtain a passing score.

The public plan and study-freeze files are clearly marked **analysis projections created after measurement**, with the original source SHA256 commitments. They preserve the same episode identities, models, arms and repetitions while removing operational hosts, paths and authorization machinery. They are not executable grants and do not pretend to recreate the historical freeze. `PROVENANCE.json` lists source hashes, metadata removed and hash links rebound; it confirms equality of the entire laboratory/public report except its path/hash provenance and exact equality of both language reports.

This is exact **recalculation of recorded evidence**. Requesting new model answers is a different operation: it needs a provider and its costs, may yield different text, and must record requested/returned model versions and limits. This archive does not promise immutable model weights, bit-identical future answers, or fleet-wide Hermes behavior.

## Public component and technical reproduction

The public component is installed from the `Musyg/persistent-memory` repository using its existing Python package:

```sh
# Run from the downloaded repository root, separately from offline reporting.
python3 -m pip install .
```

The qualified benchmark candidate adds `--trajectories` to the repository's existing `benchmarks/run_benchmark.py`; its source SHA256 is `641c1a20f879cf914babbed9b0be6119aa90f4d528791b17401e574a40059991`. Use a repository revision containing that exact file; a previous release may not yet expose the option.

Examples, from that qualified repository version:

```sh
python3 benchmarks/run_benchmark.py --trajectories 3000 --seed 20261021
python3 benchmarks/run_benchmark.py --documents 100 --repetitions 100 --seed 20261021
python3 benchmarks/run_benchmark.py --documents 1000 --repetitions 1000 --seed 20261021
```

These local checks require no model API. Runtime/resource limits and exact recorded seeds belong to their technical evidence. The 5,000-source run reached its 40-minute limit and remains unqualified; these commands do not silently repeat that load or turn its timeout into a pass. A technical trajectory count is separate from the 500 business tasks and model-answer evaluation.
