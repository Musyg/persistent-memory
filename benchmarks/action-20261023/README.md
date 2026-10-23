# Memory transfer into verified files

[Français](README.fr.md) · [Synthetic fixture](FIXTURE.json) · [Cell plan](PLAN.json)

The fresh-parameter study closed with **486 correct outcomes, 89 wrong actions and one unknown out of 576 calls**. Memory-supported arms outperformed no memory on these synthetic tasks. Typed memory did not outperform strong versioned lexical retrieval.

## Fresh-parameter results

Each row contains 72 calls. P2 completed 575 calls; one Luna no-memory call returned HTTP 500 and remains unknown. There were no schema refusals.

| Model | Arm | Correct | Wrong | Unknown |
| --- | --- | ---: | ---: | ---: |
| GPT-6 Luna | Typed memory | 66 | 6 | 0 |
| GPT-6 Luna | Strong versioned lexical | 67 | 5 | 0 |
| GPT-6 Luna | Authorized history | 66 | 6 | 0 |
| GPT-6 Luna | No memory | 35 | 36 | 1 |
| GPT-6.1 Sol | Typed memory | 72 | 0 | 0 |
| GPT-6.1 Sol | Strong versioned lexical | 72 | 0 | 0 |
| GPT-6.1 Sol | Authorized history | 72 | 0 | 0 |
| GPT-6.1 Sol | No memory | 36 | 36 | 0 |
| **Total** | | **486** | **89** | **1** |

For Luna, typed memory exceeds no memory by 41.67–43.06 percentage points, retaining both possibilities for the unknown; the nominal 95% cluster-bootstrap interval is +25.00 to +52.78 points. Sol gains 50 points, with a degenerate [50, 50] interval in these synthetic strata—not universal certainty. Luna typed memory versus lexical retrieval is −1.39 points, interval [−4.17, 0]; Sol ties. These results support useful transfer on this set, not general dominance.

The native report passed. Registry independently checked 576 current-authority cases across 24 partitions and freshly verified 575 available file outcomes, preserving 486 successes, 89 failures and one unknown. All 13,672 historical files remained unchanged. [Confirmation observations](confirmation/OBSERVATIONS.json) · [Native result](confirmation/RESULT.json) · [Protocol](confirmation/PROTOCOL.md).

## Initial study: retained negative result

The first closed study produced **45 correct file outcomes out of 576 model calls (7.8%)**. All P2 processes completed; no outcome is unknown. There were 493 schema refusals and 38 accepted proposals that incorrectly held the task. No memory advantage is established.

Each row contains 72 calls. Schema refusals are host envelope rejections. Rejected business actions were not validated.

| Model | Arm | Correct | Schema refusal | Wrong hold |
| --- | --- | ---: | ---: | ---: |
| GPT-6 Luna | Typed memory | 1 | 69 | 2 |
| GPT-6 Luna | Strong versioned lexical | 1 | 65 | 6 |
| GPT-6 Luna | Authorized history | 3 | 67 | 2 |
| GPT-6 Luna | No memory | 2 | 64 | 6 |
| GPT-6.1 Sol | Typed memory | 10 | 56 | 6 |
| GPT-6.1 Sol | Strong versioned lexical | 9 | 59 | 4 |
| GPT-6.1 Sol | Authorized history | 12 | 60 | 0 |
| GPT-6.1 Sol | No memory | 7 | 53 | 12 |
| **Total** | | **45** | **493** | **38** |

The interface was underspecified: the prompt never explicitly named the required `schema` key, and selected source identifiers were absent from the rendered memory. Self-contained tasks were also unnecessarily held. Rejected proposals remain unvalidated. The original source, responses and scores remain frozen.

An offline Registry assessment freshly reopened all 576 file outcomes across 24 partitions. It preserved 45 successes, 531 failures and all 12,802 original files.

## Method and controls

The 24 synthetic worlds comprise 12 French and 12 English cases, independently parameterized within 12 templates. Four families cover procedures, corrections, withdrawals and self-contained requests. Two models, four arms and three repetitions give 576 calls, not independent capabilities.

Typed memory, strong versioned lexical retrieval and authorized chronological history share version, withdrawal, workspace and eligibility checks. History masks superseded, withdrawn and ineligible bodies. The fourth arm has task inputs only. All use a five-item, 2,000-character ceiling; history fits without truncation. This does not equalize prompts or realized spending.

P1 deterministically persists observations and exits. Fresh P2 opens memory and obtains one JSON proposal, limited to two CSV/JSON writes to allowed targets. Authority is rechecked before dependent writes. After P2 exits, fresh P3 reopens files against independent exact-byte and typed JSON/CSV expectations hidden from the model. Every task includes a positive control; holding everything cannot pass. This evaluates transfer, not autonomous learning.

## Reproduction, accounting and calibration

Use Linux, both packages, hash-pinned fixture/plan and the existing benchmark CLI. Original commit: `a67c611fbabc75f31a87bc2c834740dd51414080`. Two environments each passed 12 application tests, 192 simulated cells and four mock client/budget tests: plumbing evidence only.

From the repository root, in a fresh Linux environment, reproduce the first report offline:

```sh
python -m pip install . ./packages/policy-registry
study=benchmarks/action-20261023
obs="$study/initial/OBSERVATIONS.json"
obs_sha=$(sha256sum "$obs" | cut -d' ' -f1)
test "$obs_sha" = 28d14498adce39ef47c67833e17e8444061b28af24e436632012ff85bd1a8808 || exit 1
python -I -B benchmarks/run_benchmark.py --action-report "$obs" --action-report-sha256 "$obs_sha"
```

The SHA covers the **whole raw OBSERVATIONS.json file**, not selected rows or an embedded field. Evidence: [initial observations](initial/OBSERVATIONS.json), [initial result](initial/RESULT.json), [calibration readiness](calibration/READINESS.json), [calibration provenance](calibration/PROVENANCE.json).

Reproduce confirmation with its whole-file SHA and explicit fixture/plan bindings:

```sh
obs="$study/confirmation/OBSERVATIONS.json"
obs_sha=$(sha256sum "$obs" | cut -d' ' -f1)
test "$obs_sha" = 07836b70b76e3012c8db4e5b2736bb3ac83ab22bc4a8ea1feca58e1b4309c02f || exit 1
python -I -B benchmarks/run_benchmark.py \
  --action-report "$obs" --action-report-sha256 "$obs_sha" \
  --action-fixture "$study/confirmation/FIXTURE.json" \
  --action-fixture-sha256 763af4de662fc6002ebf9bdbf901a7df623f3d0a97f23c01792e15d28f315ae8 \
  --action-plan "$study/confirmation/PLAN.json" \
  --action-plan-sha256 e08ab03cd7c9cbb6659a853c34301a03f351d7e0a12f18cf240826604ce1982f
```

Run the bounded application and analysis tests offline with local file bindings; no PYTHONPATH is needed under `-I`:

```sh
ACTION_SOURCE="$PWD/benchmarks/action_transfer.py" \
ACTION_FIXTURE="$PWD/$study/FIXTURE.json" \
ACTION_BENCHMARK="$PWD/benchmarks/run_benchmark.py" \
python -I -B -m unittest discover -s "$study/tests" -p test_action_transfer.py

ACTION_ANALYSIS="$PWD/benchmarks/run_benchmark.py" \
ACTION_BENCHMARK="$PWD/benchmarks/run_benchmark.py" \
ACTION_FIXTURE="$PWD/$study/FIXTURE.json" ACTION_PLAN="$PWD/$study/PLAN.json" \
ACTION_VOLUME_ANALYSIS="$PWD/benchmarks/validation-20261022/CODE/volume_analysis.py" \
python -I -B -m unittest discover -s "$study/tests" -p test_action_analysis.py
```

Analysis reuses paired bootstrap observations across 12 template clusters and four family strata: 10,000 draws, seed 20261023. Usage is known for 575/576 calls, but only 527 are priceable at frozen October 23, 2026 tariffs: 48 report unsupported cache-write usage and one lacks usage. The $0.6927518 known subtotal is not the full cost or invoice. Reasoning is counted once; latency covers P2 only. No equal-spending frontier is established.

The prompt repair preserves parser, security checks and oracles; the earlier provenance fix separates task input from memory. Offline qualification passed. Known-data calibration then produced **47/48 correct outcomes**, with 48 accepted schemas, controls and unique calls. Luna sorted an English catalog merge ascending instead of descending in catalog.json: a genuine task failure. This memory-ON-only subset supplies no independent benefit estimate or direct comparison with the original study.

The original 48/48 gate remains failed. After independent semantic review, an [explicit prospective amendment](https://github.com/Musyg/persistent-memory/blob/0eb33107ac5742ee3fcf6ab85da6acdf24cc799a/benchmarks/action-20261023/confirmation/PROTOCOL.md) admitted one new 576-call study, frozen before any fresh response. This is a declared change to the continuation criterion, not a pass under the original gate.

The study uses fresh parameters for the same 12 templates. The qualified prompt and support remain unchanged (SHA256 `74138918d82aa405261e60d1e7a258bbbc4e2dec6c629c7017ef8e381c35d9e4`), as do parser, oracles, models, arms and analysis. No retries, prompt tuning or further calibration are permitted. All responses, failures and unknowns are retained for publication. Calibration is excluded from independent benefit estimates. The new study is closed; its results appear above. Original failures remain unchanged.
