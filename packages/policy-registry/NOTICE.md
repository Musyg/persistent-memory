# Generic contract provenance

The bundled `hermes_policy_registry/contracts/learning_records.py` is a byte-preserved extraction of newly authored generic Hermes learning-record contracts, not a dump of the Learning Engine or any database. SHA256: `3dd069650457f2ecb7ddacf13c7cba8a7b76ef459d8bb6228d699b16fa7c720e`.

Origin history inspected: commit `d5cc810dcca1ff9df7a0a2daae1d40948bd12794` (2026-09-27, “Prepare combined LE maintenance and offline learning contracts”), followed by `fa1f7f247fd0163c9a106de7be58d677357a164e` (2026-09-27, “feat(learning): persist versioned experiences and evaluations in local ledger”). Both commits identify author `Hermes-Agency`. The module imports only Python standard-library hashlib/json/math/datetime. Inspection found no third-party copied implementation, private content, endpoints, credentials or fleet configuration in this module.

MIT licensing of this selected generic module and new registry code is authorized by the project owner for the open-source extraction. This does not relicense the private repository or any third-party code. The byte-preserved module and newly written registry/adapter are distinguished here; no external authorship guarantee beyond the inspected provenance is implied. License text: LICENSE, Copyright 2026 Musyg.

No private repository access is needed at runtime. The package bundles this exact module by default; an optional override is accepted only with the same source SHA. Changes to the contract require a separately reviewed version.
