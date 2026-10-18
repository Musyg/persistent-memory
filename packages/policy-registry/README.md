# Hermes Policy Registry

[Français](README.fr.md)

Record immutable policies, their evaluation evidence, explicit admissions and rollbacks. The registry uses SQLite and the Python standard library. It is independent of `hermes-memory-core` and needs no model, service or private data.

Five policy families can be represented: prompt, retrieval, routing, workflow and skill. Version 0.2.0a2 implements retrieval-report evaluation and native-effect assessment for retrieval and workflow policies. Representing a family does not provide an optimizer for that family.

## Install and try

Python3.11 or later. Installation, file permissions and examples are qualified on Linux.

```sh
python3 -m pip install ./packages/policy-registry
hermes-policy-demo --directory ./new-policy-demo
```

From this package directory, use `python3 -m pip install .`. The demo refuses an existing output directory. It creates synthetic sealed experience/evaluation records, proposes and evaluates a policy, admits it with an explicitly trusted fixture callback, reopens SQLite and withdraws a source. The effective state then changes from `admitted` to `rollback` while runtime activation remains false.

The bundled `fixtures/demo.json` contains **invented labels, durations and identifiers**, not retrieval measurements. It makes zero model or retrieval calls. Its callback is an example for trusted synthetic inputs, not a production authority adapter.

```sh
python3 -m unittest discover -s tests -v
hermes-policy --help
```

The source distribution includes 49 tests: 21 author tests, 14 independent registry tests, 12 independent workflow-effect tests and 2 public-demo tests. Tests construct synthetic inputs; neither a private source path nor a live backend is required.

## Contracts

`Registry.create(path, load_learning_records(), protocol)` creates an exclusive database under an existing private parent. Use `propose`, `add_report`, `add_record`, `evaluate_retrieval_reports`, `evaluate_native_effect_reports`, `evaluate_workflow_effect_reports`, `admit`, `revoke`, `rollback` and `inspect`. State changes use expected-sequence compare-and-swap.

A policy's immutable configuration identifies the exact executed policy digests, including budgets. Declared configurations must all have execution evidence. The adapter checks run, policy, source and outcome references, original record seals, rubric and judge revision. Cost and quality evidence use the same dataset; costs pair candidate and baseline by case/repetition. Duplicate cases cannot inflate the number of observations.

`evaluate_native_effect_reports` accepts the explicit `native-effects-v1` protocol. It checks immutable execution/evaluation/source links, a consumed effect independently reopened from storage, current dependencies and paired wall time covering retrieval, proposal, consumption and reopening. Its 22 synthetic qualification cases include incomplete, tampered, withdrawn and superseded evidence. Provider billing, CPU ratios, RSS and energy are not assessed. This is a Python API; the existing CLI/demo still exercises retrieval reports. It does not install a learning loop or activate a policy. See [native-effect provenance](PROVENANCE-native-effects-v1.json).

Observed false/zero means observed failure. Unavailable, not sampled and withdrawn remain unobserved. A later correction or withdrawal invalidates the previous assessment; source revocation makes dependent admission ineffective. Records remain available. A rollback is terminal for an artifact; revised code or configuration has a new identity.

Admission requires a fresh external dependency-validation callback. The caller must connect it to a trusted authority. The registry cannot authenticate that callback or the judge, and does not deploy, execute or select an active policy. Permission changes are outside the learning process.

The existing `hermes-policy pilot --r3-report ... --r4-report ... --output ...` command accepts the adapter's precise versioned report format. It imports supplied measurements and refuses automatic activation. Such reports are not bundled: the standalone synthetic demo above is the supported zero-input walkthrough. The schema examples in the tests show exact report bindings. An optional `--learning-records` override must match the bundled contract hash.

## Workflow effects (0.2.0a2)

`Registry.evaluate_workflow_effect_reports(policy_ref, run_links, cost_report_ref, expected_seq, revalidate, verify_effect)` assesses the explicit `native-workflow-effects-v1` protocol for the `workflow` family. Reports bind the rule, oracle, dataset, executed configuration, sealed experience/evaluation and consumed effect. The rule, oracle and dataset references must be declared dependencies; the oracle must match the configured rubric.

The host supplies `verify_effect`. It receives a detached JSON envelope containing `schema`, `rule_ref`, `oracle_ref`, `dataset_ref` and `run`. It must independently reopen the actual effect, compare it with the expected outcome and verify the evaluation label. A positive reply has exactly `status: "verified"`, `effect_ref`, `rule_ref`, `oracle_ref` and `dataset_ref`, with matching immutable identities. A report's own acknowledgement or reopening marker is insufficient. The separate `revalidate` callback freshly checks the complete dependency chain.

The adapter retains compare-and-swap, duplicate-case rejection, source withdrawal, evaluation supersession and paired cost checks. Its twelve independent tests use synthetic SQLite effects, including forged success, wrong outcomes, missing verification, stale identities and rollback. Their constructed cost samples test bindings only, not performance. The registry records assessment and explicit admission; a trusted host remains responsible for applying or reverting real workflow behavior. Neither this API nor the unchanged retrieval demo deploys a workflow or trains model weights. See [workflow provenance](PROVENANCE-workflow-effects-v1.json).

## Boundaries

Hashes provide identity and consistency, not signatures or authenticated measurements. This version trusts local filesystem control, does not protect against rollback of the entire registry database, has no distributed transaction or per-user ACL, and offers no exactly-once transport retry guarantee. SQLite commit outcomes can be uncertain after a crash.

Individual canonical reports are limited to8MiB and one evaluation to256 run links. Total history/DB size has no comprehensive quota; large-history performance is not qualified. Linux is the tested platform. See [NOTICE.md](NOTICE.md) for generic-contract provenance and [LICENSE](LICENSE) for MIT terms.
