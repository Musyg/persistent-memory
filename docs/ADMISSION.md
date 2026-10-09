# Admit a reviewed card or a useful notice

[Français](ADMISSION.fr.md) · [Structured contracts](STRUCTURED.md) · [README](../README.md)

`hermes_memory.admission` exports `admit(request, authority, sink, transform=None)` and `LabOrchestratorSink`. The boundary is synchronous, standard-library only and opt-in. It accepts a **trusted host's review dossier**, not untrusted model assertions of their own sufficiency. No extraction, provider, RPC, database, service or automatic production adoption is included.

```python
from hermes_memory.admission import admit, LabOrchestratorSink
from hermes_memory.admission_demo import example_request, demo_authority

sink = LabOrchestratorSink()
result = admit(example_request(), demo_authority, sink)
assert result['envelope']['decision'] == 'admitted'
assert result['handoff']['delivery'] == 'acknowledged'
```

Run `python -m hermes_memory.admission_demo` for eight synthetic outcomes. Its authority always makes local example decisions; replace it with your separately authenticated host authority before a real integration. A sink ACK means only that the callback returned the expected acknowledgment.

## Reviewed input

The exact request keys are `schema, brief, accepts_format, workspace, limits, sources, dossier, c1_request`:

- Schema is `hermes.admission.request.v1`. `brief` is nonempty, at most 8,192 characters, and neither parsed nor returned. `accepts_format` is a host Boolean attestation that a technical card or fixed notice fits the intention.
- `limits` has integer `min_words, max_words` from 1 to 10,000. Limits apply to cards and notices.
- `sources` contains at most 16 metadata dictionaries `{id, workspace, version, sha256, state}`. Raw source text is supplied only inside the structured request when applicable.
- `dossier` is `{reviewer, status, necessary_source_ids}`. Status is `supported`, `unknown`, `conflict` or `not_reviewed`; reviewed statuses require a reviewer identifier. The host must identify all evidence needed for the conclusion, including counterevidence. The library cannot prove this list complete.
- `c1_request` is null for non-supported dossiers. A supported dossier supplies the [structured request](STRUCTURED.md), same workspace/word bounds/source metadata, 1–4 required facts on one subject; every rendered source must belong to the necessary source list.

The original request is copied after bounded exact-type validation: JSON dictionaries/lists/strings/integers/Booleans/null, no tuples/subclasses/floats; canonical size ≤300,000 bytes, depth ≤16, nodes ≤16,384, collection entries ≤64. Callback mutations cannot alter that captured input. Concurrent mutation during capture is outside the contract. An invalid request invokes neither authority nor sink.

## Authority and the unique handoff

`authority(snapshot, stage)` receives only `{workspace, sources:[{id, version, sha256}]}`, ordered by necessary source IDs, at `before` and `before_handoff`. It receives no brief or evidence text. Its response is exactly `{status, revision, disclose_withdrawal}`:

| Status | Revision | Meaning |
|---|---|---|
| allowed | identifier | Continue only if both checks agree. |
| revoked | identifier | `withdrawn` if disclosure is true, otherwise `access_unavailable`. |
| denied | identifier | `access_unavailable`, regardless of disclosure flag. |
| unavailable | null | `authority_unavailable`. |

`disclose_withdrawal` must be Boolean. Missing callbacks, malformed responses and exceptions are unavailable. An allowed revision change yields `authority_changed`; a locally withdrawn source cannot be resurrected by the callback.

These two stages apply when the request reaches preparation. An initial authority refusal returns its sanitized notice immediately. For a host-declared unsupported intention, the supplied payload has already been traversed and copied during input capture, including any evidence bodies it contains. That branch returns only its generic notice without C1 preparation/rendering or an authority/transform call. The function does not fetch external evidence. Invalid requests invoke no callback.

Optional `transform(body_bytes)` runs once on a prepared nonempty body and must return exactly the same bytes. Modification, exception or malformed output yields `consumer_changed`. The final authority check still runs and can override that result; an access-loss notice is reconstructed and is not transformed again. Buffer comparison occurs **before** the unique sink call, not after consumption.

`sink(envelope, receipt)` receives separate copies only for a nonempty admissible card/notice. Expected ACK is exactly `{status:'received', body_sha256:<received body's SHA-256>}`. Handoff records `attempted` (0/1), `delivery` (`not_attempted`, `acknowledged`, `unknown`) and a generic incident. An exception after an effect remains one attempted delivery with unknown outcome; exception text is not exported and there is no retry. The host decides any subsequent recovery with knowledge of its consumer's effects.

## Output and limits

Return value has `envelope`, `receipt`, `handoff`. Envelope carries decision, body kind (`technical_card`, `notice`, `none`), body/new body hash, opaque request ID, contract revision, authority revision, evidence review, consumer verification and `publication_atomic=False`. Receipt adds cause, admitted provenance and `extraction_measured=False`.

Decisions distinguish `admitted`, `unknown`, `conflict`, `unsupported_intent`, `review_required`, `withdrawn`, `access_unavailable`, `authority_unavailable`, `authority_changed`, `consumer_changed`, `output_constraint` and `invalid_request`. Unknown evidence is not a transport outage, and an unsupported template is not proof an intention cannot be satisfied by another approach. A word limit too small even for a notice yields no body with `output_constraint`.

On access loss, the exported envelope and receipt contain no prior source IDs, provenance, original body hash or supported/conflict review state: review becomes `not_disclosed`, authority revision null and provenance empty. Only the new permitted notice's hash remains. By contrast, an admitted private receipt intentionally includes the authorized source span; protect that receipt as evidence, and do not publish it by default.

Host review proves neither semantic entailment nor extraction accuracy. Identity/authentication, authority availability, storage, callback deadlines, atomic authorization/publication, downstream consumption and recall of previously delivered copies are not supplied here. The bound is on accepted data, not arbitrary callback duration or hostile Python code. See [loading and counter limits](STRUCTURED.md) and the synthetic tests before integrating.

Exception handling described above covers ordinary `Exception` subclasses. An interruption or other `BaseException` can escape without a returned receipt, including after a consumer effect. No durable journal or callback sandbox is provided. The host must handle interruptions and any uncertain effects separately.
