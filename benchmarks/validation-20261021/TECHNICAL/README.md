# Historical technical evidence

These files project technical receipts recorded on 21 October 2026 for publication. Measured values, test identifiers, synthetic cases, counters, expected faults and expected rejections are preserved. Absolute paths, machine identities, logs and transport envelopes are excluded. Environments are labelled A and B; the original receipts remain private and unchanged.

| Historical check | Preserved result |
|---|---|
| Installed distributions, A and B | Per environment: 147 core wheel tests + 147 sdist + 49 policy wheel + 49 sdist = 392 executions, with zero failures, errors or skips. Imports from site-packages are attested separately without inventing a public installation path. |
| Technical trajectories, A and B | The same 3,000 cases across six families of 500, reproduced in both environments: 86,965 explicit calls, 57,763 read invariants, 1,000 expected caught faults and 1,000 expected rejections per environment. These are 3,000 unique trajectories, not 6,000 independent clients or tasks. |
| Load 100, A and B | 100 searches in each environment. B reproduces only this scale; no 1,000- or 5,000-source measurement is attributed to B. |
| Load 1,000, A | 1,000 searches; p50 0.3781398144783452 s, p95 0.38777976483106613 s. Ingestion took 76.00318102305755 s; these timings remain separate from search latency. |
| Load 5,000, A | An actual 40-minute runtime timeout, without a user-requested stop. No final report; the phase and partial operation count are unknown. This scale is not qualified. The timeout does not establish a semantic failure. |

The two trajectory reports and two environment-A load reports retain the exact bytes embedded in their receipts, checked against the terminal file hashes. Projected outcome summaries also retain worker durations, separate from internal benchmark timings. The B load result preserves the complete case and its report. Distribution evidence retains every `test_id`, error, counter and test-source parity result.

Repeated wheel/sdist runs do not constitute 784 independent guarantees.

`BENCHMARK-SOURCE-PINS.json` distinguishes the revisions actually exercised: load SHA256 `66ebda8d8f297c25c63c5fcc9f2839089d95d33921a1137af9fbabb26e4b8766`, trajectories SHA256 `641c1a20f879cf914babbed9b0be6119aa90f4d528791b17401e574a40059991`. Historical receipts are not relabelled as qualification of a future commit or newly built distributions.

Load latency covers `typed.search`, excluding explicit `memory.read` checks. Cold cache was not controlled. Peak RSS is a process-lifetime high-water mark, not incremental memory usage. Queries use synthetic lexical tokens; they do not assess ranking quality or autonomous business tasks. These benchmarks made no provider calls. Their document counts are distinct from the 500 tasks in the answer evaluation.

`PROVENANCE.json` supplies private-receipt hashes, logical locations, removed fields and common digests of retained values. `INSTALLED-ORIGIN-ATTESTATIONS.json` explains how installed origins are projected. `VERIFICATION.json` records document-extraction checks only, with no new benchmark. `MANIFEST.json` and `SHA256SUMS` bind the public bytes. This projection was created after measurement; it is neither an externally timestamped preregistration nor a certificate for the entire Hermes production system. Root must still qualify the final public tree before promotion.
