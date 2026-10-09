"""A fresh synthetic reviewed card and explicit refusal/handoff examples. No I/O except stdout."""
import hashlib
import json

from .admission import LabOrchestratorSink, admit
from .quality_contract import OutputContract, validate_output


def example_request(status='supported'):
    """Construct reviewed synthetic inputs; this is not a free-text extractor."""
    text = 'Le capteur de démonstration indique une durée de 12 ms en mode essai.'
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    metadata = dict(id='demo-note', workspace='demo', version='v1', sha256=digest, state='active')
    fact = dict(id='duration', subject='capteur de démonstration', property='durée',
                value=dict(type='number', value='12'), unit='ms', polarity='positive',
                scope='mode essai', cardinality='single', source_id='demo-note',
                source_version='v1', source_sha256=digest,
                span=dict(start=0, end=len(text), text=text), origin='document', certainty='asserted')
    structured = dict(schema='hermes.structured.request.v1', workspace='demo',
                      sources=[dict(metadata, text=text)], facts=[fact],
                      plan=dict(fact_ids=['duration'], required_ids=['duration']),
                      contract=dict(language='fr', min_words=1, max_words=120,
                                    max_candidates=8, allow_repair=True))
    return dict(schema='hermes.admission.request.v1', brief='Présenter la durée en mode essai.',
                accepts_format=True, workspace='demo', limits=dict(min_words=1, max_words=120),
                sources=[metadata], dossier=dict(reviewer='demo-review', status=status,
                                               necessary_source_ids=['demo-note']),
                c1_request=structured if status == 'supported' else None)


def demo_authority(snapshot, stage):
    """Synthetic host decision, not authenticated production identity."""
    return dict(status='allowed', revision='demo-authority-v1', disclose_withdrawal=False)


def run_demo():
    observations = []

    def record(name, result, expected):
        envelope = result['envelope']
        assert envelope['decision'] == expected, name
        assert envelope['publication_atomic'] is False
        assert result['receipt']['extraction_measured'] is False
        observations.append(dict(example=name, decision=envelope['decision'],
                                 body_kind=envelope['body_kind'], body=envelope['body'],
                                 handoff=result['handoff']))

    sink = LabOrchestratorSink()
    card = admit(example_request(), demo_authority, sink)
    record('reviewed_card', card, 'admitted')
    check = validate_output(card['envelope']['body'], OutputContract(1, 120, 'fr', ('demo-note',)))
    assert check['mechanical_pass'] and check['semantic_status'] == 'not_evaluated'
    assert sink.calls == 1 and card['handoff']['delivery'] == 'acknowledged'

    for decision in ('unknown', 'conflict'):
        record(decision, admit(example_request(decision), demo_authority, LabOrchestratorSink()), decision)

    def withdrawal(snapshot, stage):
        return (dict(status='revoked', revision='demo-authority-v2', disclose_withdrawal=True)
                if stage == 'before_handoff' else demo_authority(snapshot, stage))

    withdrawn = admit(example_request(), withdrawal, LabOrchestratorSink())
    record('withdrawal_before_handoff', withdrawn, 'withdrawn')
    assert withdrawn['receipt']['provenance'] == []
    assert withdrawn['receipt']['evidence_review'] == 'not_disclosed'
    record('missing_authority', admit(example_request(), None, LabOrchestratorSink()), 'authority_unavailable')

    changed_sink = LabOrchestratorSink()
    changed = admit(example_request(), demo_authority, changed_sink, transform=lambda body: body+b' ')
    record('changed_buffer', changed, 'consumer_changed')
    assert changed_sink.calls == 0 and changed['handoff']['attempted'] == 0

    too_short = example_request()
    too_short['limits']['max_words'] = too_short['c1_request']['contract']['max_words'] = 1
    record('unmet_word_limit', admit(too_short, demo_authority, LabOrchestratorSink()), 'output_constraint')

    effects = []
    def effect_then_failure(envelope, receipt):
        effects.append(envelope['body'])
        raise RuntimeError('synthetic downstream failure')
    uncertain = admit(example_request(), demo_authority, effect_then_failure)
    record('effect_without_acknowledgment', uncertain, 'admitted')
    assert len(effects) == 1
    assert uncertain['handoff'] == dict(attempted=1, delivery='unknown', incident='sink_exception')
    return dict(passed=True, synthetic=True, provider_calls=0, extraction_measured=False,
                publication_atomic=False, acknowledgment_proves_consumption=False,
                examples=observations)


def main():
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
