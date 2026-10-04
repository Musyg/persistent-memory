# Hermes Policy Registry

[Français](README.fr.md)

Record immutable policies, their evaluation evidence, explicit admissions and rollbacks. The registry uses SQLite and the Python standard library. It is independent of `hermes-memory-core` and needs no model, service or private data.

Five policy families can be represented: prompt, retrieval, routing, workflow and skill. This version implements **one retrieval-report evaluation adapter**. Representing a family does not provide an optimizer for that family.

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

The source distribution includes20 author tests,14 independent tests and2 public-demo tests. Tests construct synthetic inputs; neither a private source path nor a live backend is required.

## Contracts

`Registry.create(path, load_learning_records(), protocol)` creates an exclusive database under an existing private parent. Use `propose`, `add_report`, `add_record`, `evaluate_retrieval_reports`, `admit`, `revoke`, `rollback` and `inspect`. State changes use expected-sequence compare-and-swap.

A policy's immutable configuration identifies the exact executed policy digests, including budgets. Declared configurations must all have execution evidence. The adapter checks run, policy, source and outcome references, original record seals, rubric and judge revision. Cost and quality evidence use the same dataset; costs pair candidate and baseline by case/repetition. Duplicate cases cannot inflate the number of observations.

Observed false/zero means observed failure. Unavailable, not sampled and withdrawn remain unobserved. A later correction or withdrawal invalidates the previous assessment; source revocation makes dependent admission ineffective. Records remain available. A rollback is terminal for an artifact; revised code or configuration has a new identity.

Admission requires a fresh external dependency-validation callback. The caller must connect it to a trusted authority. The registry cannot authenticate that callback or the judge, and does not deploy, execute or select an active policy. Permission changes are outside the learning process.

The existing `hermes-policy pilot --r3-report ... --r4-report ... --output ...` command accepts the adapter's precise versioned report format. It imports supplied measurements and refuses automatic activation. Such reports are not bundled: the standalone synthetic demo above is the supported zero-input walkthrough. The schema examples in the tests show exact report bindings. An optional `--learning-records` override must match the bundled contract hash.

## Boundaries

Hashes provide identity and consistency, not signatures or authenticated measurements. This version trusts local filesystem control, does not protect against rollback of the entire registry database, has no distributed transaction or per-user ACL, and offers no exactly-once transport retry guarantee. SQLite commit outcomes can be uncertain after a crash.

Individual canonical reports are limited to8MiB and one evaluation to256 run links. Total history/DB size has no comprehensive quota; large-history performance is not qualified. Linux is the tested platform. See [NOTICE.md](NOTICE.md) for generic-contract provenance and [LICENSE](LICENSE) for MIT terms.
