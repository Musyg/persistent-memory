# Test selection and reproducibility

Core: 47 unchanged synthetic tests. Typed retrieval R3: 16 author, 14 independent inherited R3, 5 edge regressions. Integration R3: 20 portable author tests and 16 independent HTTP/client tests. Product assembly: separate tests for installed CLI, generic tool registration, the two-actor demo and refusing an existing example directory.

The original application's private orchestrator AST test, builder and source are excluded. Its prior private execution is not counted as a test of this distribution. Assertions in selected tests retain their original meaning. Adaptations are limited to package imports, installed-core path discovery, test-base naming to avoid duplicate discovery, and module CLI paths; see `PROVENANCE.json`.

Tests use temporary synthetic stores and loopback servers. There are no model weights, embeddings from users, provider calls or private databases. Tests of source hashes deliberately require the exact core and typed R3 versions. Editing those files requires an explicit compatibility review and hash update; installing a different version silently is not supported.

Build wheel and sdist with `python -m build`. Install the wheel into a fresh Linux venv, change directory outside the checkout, and use `python -m unittest discover -s /absolute/source/tests -v`. Also install a wheel rebuilt from the sdist to verify distribution completeness. The source checkout must not appear on PYTHONPATH when verifying installed imports.

The small benchmark generates its own 24 notes. Its timing reflects the running machine, filesystem cache and current interpreter. It has no statistical power to establish broad production superiority. The frozen R3 retrieval policy previously exceeded a 1.20 relative latency threshold in a bounded synthetic comparison despite improving evidence selection. That limitation is retained; experimental optimizations are not implicitly promoted.

## Structured rendering and admission

The opt-in APIs add eleven author regression methods and twelve independently designed package-boundary methods. Their forty-five synthetic variants cover import order, source bytes, canonical type identity, reviewed provenance, mechanical limits, notices, final authority decisions and uncertain handoff. These fixtures were fixed before the package candidate was inspected; they are published regression fixtures, not an ongoing hidden holdout or a statistical measure of answer quality. All four installed wheel/sdist suites must run without skips. The distribution checker also requires byte-identical test .py/.json inventories between the candidate and its source archives.
