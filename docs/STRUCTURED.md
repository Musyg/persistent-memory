# Structured facts and mechanical output contracts

[Français](STRUCTURED.fr.md) · [Admission](ADMISSION.md) · [README](../README.md)

These opt-in, synchronous standard-library APIs render **already reviewed structured facts** in finite French templates. They do not extract facts, establish truth, or infer whether a source implies a claim. Imports share one verified implementation graph; default `import hermes_memory` remains unchanged.

```python
from hermes_memory.structured_memory import render, canonical
from hermes_memory.quality_contract import OutputContract, validate_output
from hermes_memory.admission_demo import example_request

request = example_request()['c1_request']  # fresh synthetic reviewed input
def authority(snapshot, stage):
    return {'status': 'allowed', 'revision': 'demo-v1'}
result = render(request, authority)
assert result['status'] == 'ok'
report = validate_output(result['body'], OutputContract(1, 120, 'fr', ('demo-note',)))
assert report['mechanical_pass']
assert report['semantic_status'] == 'not_evaluated'
```

## Input and rendering

`render(request, authority)` accepts an exact dictionary with `schema='hermes.structured.request.v1'`, `workspace`, `sources`, `facts`, `plan`, and `contract`. `admission_demo.example_request()` supplies a complete editable example. The domain is intentionally small:

| Field | Contract |
|---|---|
| sources | At most 16 dictionaries: `id, workspace, version, sha256, text, state`. UTF-8 text at most 16,384 bytes; digest matches text; state active/revoked. |
| facts | At most 32 dictionaries: `id, subject, property, value, unit, polarity, scope, cardinality, source_id, source_version, source_sha256, span, origin, certainty`. |
| value | `{type, value}` with text or a decimal **string**; numbers preserve their spelling and units. No numeric inference/conversion. |
| span | `{start, end, text}`: selected facts require an exact nonempty Unicode code-point slice of the identified version. |
| plan | `fact_ids` contains 1–8 unique selected IDs; nonempty `required_ids` is a subset. |
| contract | `language='fr'`, integer word bounds 1–10,000, `max_candidates` 1–64, Boolean `allow_repair`. |

Identifiers match `[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}`. Subject/property/scope are nonempty and at most 80 characters; text values at most 160, units at most 40, decimal strings at most 40. Literal text is trimmed, single-spaced, and excludes controls, surrogates and `[]«»`. Unit is empty for text values. Selected facts must be asserted, single-valued, and originate from `document` or `brief_fact`; `instruction` is never rendered as a fact. Unselected well-shaped facts are not semantically validated. Opposing selected assertions are rejected conservatively; synonyms are not reconciled.

Original types must be exact JSON types, including integers rather than Boolean offsets/bounds. Canonical request size is at most 262,144 bytes, checked before encoding. `canonical(value)` itself is the ordinary JSON helper: UTF-8, sorted keys, `ensure_ascii=False`, compact separators and `allow_nan=False`; it does not independently enforce the request bound.

Compact positive form: `« subject » : « property » = VU ; portée « scope ». [source_id]`. Negative polarity uses `≠`. Expanded positive form: `Pour la portée « scope », la propriété « property » de « subject » a pour valeur VU. [source_id]`; negative uses `n'a pas pour valeur`. Text V is quoted; a unit adds ` unité « unit »`. These are the only two formulations. Repair explores their bounded combinations and optional omissions, keeping every required fact. It does not rewrite the claim with a model. A grammar/search failure does not prove the user's intention intrinsically impossible.

## Authority, result and counting

The callback receives a fresh metadata snapshot and stages `before`/`after` around the selected candidate. It returns exactly `{status, revision}`: `allowed` or `revoked` with an identifier revision; `unavailable` with `None`. Exceptions or malformed responses are unavailable. Changed revisions refuse the output. This callback is supplied by the host; the example is not authenticated identity or a publication transaction.

The result contains status/reason/body, request hash, word count, selected fact IDs/coverage, attempts, authority checks and provenance. Each rendered segment binds fact hash, source ID/version/hash, exact source span and output offsets/hash. Non-success returns no factual body. `semantic_status='not_evaluated'` and `publication_atomic=False` remain explicit. Statuses include `ok`, invalid/unsupported/ambiguous input, constraint/search exhaustion and authority refusal; consult the returned status rather than treating any empty result as an unknown fact.

`OutputContract(min_words, max_words, language='fr', allowed_citation_ids=('brief',))` is immutable; `from_mapping()`/`to_dict()` provide exact dictionaries. `validate_output(text, contract)` accepts at most 65,536 UTF-8 bytes. It removes complete square-bracket citations, then counts Unicode whitespace-separated tokens. Apostrophes and hyphens do not split tokens. Empty output, word bounds, unknown citations or malformed brackets fail mechanically. Language and semantic truth are not evaluated. Invalid contracts/types raise `ContractError`.

The same facade exports `make_initial_prompt`, `make_repair_prompt`, `VERSION`, `WORD_COUNT_RULE`, `MAX_TEXT_BYTES`, `MAX_PROMPT_BYTES`; prompt helpers construct local strings only. They do not call a provider. Output/prompt length caps are not process-memory quotas.

## Verified loading boundary

The three exact source resources and MIT provenance are listed in installed `hermes_memory/ADMISSION-PROVENANCE.json`. All facade imports use a locked shared graph, preserving function/class identities. The loader checks all three sizes and SHA-256 digests with expected-size-plus-one reads on each explicit loading call, including cached loads. Missing/changed resources, occupied reserved module names, inconsistent cached identities or failed construction raise a generic `ImportError`. Failed construction removes only its own registrations. Ambient top-level homonyms are not executed.

This is integrity checking at a loading boundary, not a Python sandbox, filesystem transaction, or recheck on every later function invocation. The unchanged source bootstraps use ordinary reads for their fixed installed siblings. Do not mutate installed resources or `sys.modules` concurrently. Fresh-process tests exercise copied disposable packages; do not tamper with a live installation.
