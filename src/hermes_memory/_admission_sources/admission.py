"""A1 laboratory admission boundary. No extraction, network or durable logs."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import uuid


C1_SHA256 = '4febba12532671486bdb82e1eb39009cd7bb10206e33c10d46807e718da99697'
_path = Path(__file__).resolve().with_name('structured_memory.py')
_raw = _path.read_bytes()
if hashlib.sha256(_raw).hexdigest() != C1_SHA256:
    raise ImportError('pinned_c1_mismatch')
_spec = importlib.util.spec_from_file_location('_hermes_a1_pinned_c1', _path)
_c1 = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _c1
exec(compile(_raw, str(_path), 'exec'), _c1.__dict__)
del _raw
_counter = _c1._counter  # Same pinned mechanical dependency, not a new counter.

_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z')
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_ACCESS = frozenset(('withdrawn', 'access_unavailable', 'authority_unavailable',
                     'authority_changed'))
_NOTICES = {
    'unsupported_intent': 'Cette demande ne relève pas du format de fiche technique pris en charge.',
    'unknown': "Les éléments disponibles ne permettent pas de confirmer l'information demandée dans le périmètre indiqué.",
    'conflict': "Des éléments incompatibles empêchent de confirmer l'information demandée. Une clarification est nécessaire.",
    'withdrawn': "Les éléments nécessaires ont été retirés. L'information demandée ne peut pas être fournie.",
    'access_unavailable': "L'information demandée ne peut pas être fournie dans ce contexte d'accès.",
    'authority_unavailable': "La vérification des droits est momentanément indisponible. Aucune information issue des sources n'est fournie.",
    'authority_changed': 'La référence de vérification des droits a changé. Une nouvelle vérification est nécessaire.',
    'review_required': "La fidélité des informations proposées doit encore être vérifiée. Aucune fiche factuelle n'est fournie.",
}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _clone(value):
    return json.loads(_canonical(value))


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


class _Invalid(Exception):
    pass


def _need(condition):
    if not condition:
        raise _Invalid()


def _fields(value, names):
    _need(type(value) is dict and len(value) == len(names)
          and all(type(k) is str for k in value) and set(value) == names)


def _identifier(value):
    _need(type(value) is str and len(value) <= 64 and _ID.fullmatch(value) is not None)


def _capture(value):
    """Bound original types, depth, nodes and exact JSON size before encoding."""
    size = nodes = 0

    def add(amount):
        nonlocal size
        size += amount
        _need(size <= 300000)

    def string(text):
        _need(type(text) is str and len(text) <= 262144)
        add(2)
        for char in text:
            code = ord(char)
            _need(not 0xD800 <= code <= 0xDFFF)
            if char in ('"', '\\') or char in '\b\f\n\r\t':
                add(2)
            elif code < 32:
                add(6)
            else:
                add(1 if code < 128 else 2 if code < 2048 else 3 if code < 65536 else 4)

    def walk(item, depth):
        nonlocal nodes
        nodes += 1
        _need(nodes <= 16384 and depth <= 16)
        kind = type(item)
        if kind is str:
            string(item)
        elif kind is bool:
            add(4 if item else 5)
        elif item is None:
            add(4)
        elif kind is int:
            _need(-1000000000 <= item <= 1000000000)
            add(len(str(item)))
        elif kind is list:
            _need(len(item) <= 64)
            add(2 + max(0, len(item)-1))
            for child in item:
                walk(child, depth+1)
        elif kind is dict:
            _need(len(item) <= 64)
            add(2 + max(0, len(item)-1) + len(item))
            for key, child in item.items():
                _need(type(key) is str)
                walk(key, depth+1)
                walk(child, depth+1)
        else:
            raise _Invalid()

    walk(value, 0)
    encoded = _canonical(value)
    _need(len(encoded) == size and len(encoded) <= 300000)
    return json.loads(encoded)


def _request(value):
    captured = _capture(value)
    _fields(captured, {'schema', 'brief', 'accepts_format', 'workspace', 'limits',
                       'sources', 'dossier', 'c1_request'})
    _need(captured['schema'] == 'hermes.admission.request.v1')
    _need(type(captured['brief']) is str and bool(captured['brief'].strip())
          and len(captured['brief']) <= 8192)
    _need(type(captured['accepts_format']) is bool)
    _identifier(captured['workspace'])
    limits = captured['limits']
    _fields(limits, {'min_words', 'max_words'})
    _need(type(limits['min_words']) is int and type(limits['max_words']) is int
          and 1 <= limits['min_words'] <= limits['max_words'] <= 10000)
    _need(type(captured['sources']) is list and len(captured['sources']) <= 16)
    sources = {}
    for source in captured['sources']:
        _fields(source, {'id', 'workspace', 'version', 'sha256', 'state'})
        for key in ('id', 'workspace', 'version'):
            _identifier(source[key])
        _need(type(source['sha256']) is str and _HASH.fullmatch(source['sha256']) is not None)
        _need(type(source['state']) is str and source['state'] in ('active', 'revoked'))
        _need(source['id'] not in sources)
        sources[source['id']] = source
    dossier = captured['dossier']
    _fields(dossier, {'reviewer', 'status', 'necessary_source_ids'})
    _need(type(dossier['status']) is str
          and dossier['status'] in ('supported', 'unknown', 'conflict', 'not_reviewed'))
    if dossier['status'] == 'not_reviewed':
        _need(dossier['reviewer'] is None)
    else:
        _identifier(dossier['reviewer'])
    needed = dossier['necessary_source_ids']
    _need(type(needed) is list and len(needed) <= 16)
    for item in needed:
        _identifier(item)
        _need(item in sources)
    _need(len(set(needed)) == len(needed))
    _need(type(captured['c1_request']) is dict if dossier['status'] == 'supported'
          else captured['c1_request'] is None)
    return captured, [sources[item] for item in sorted(needed)]


def _authority(callback, workspace, sources, stage):
    snapshot = {'workspace': workspace,
                'sources': [{key: source[key] for key in ('id', 'version', 'sha256')}
                            for source in sources]}
    try:
        response = callback(_clone(snapshot), stage)
        _fields(response, {'status', 'revision', 'disclose_withdrawal'})
        status, revision = response['status'], response['revision']
        _need(type(status) is str and status in ('allowed', 'revoked', 'denied', 'unavailable'))
        _need(type(response['disclose_withdrawal']) is bool)
        if status == 'unavailable':
            _need(revision is None)
        else:
            _identifier(revision)
        if status == 'allowed':
            return None, revision
        if status == 'revoked' and response['disclose_withdrawal']:
            return 'withdrawn', None
        if status in ('revoked', 'denied'):
            return 'access_unavailable', None
    except Exception:
        pass
    return 'authority_unavailable', None


def _compatible(request):
    """Structural coupling only. The trusted dossier supplies semantic review."""
    core = request['c1_request']
    _need(core['workspace'] == request['workspace'])
    for field in ('min_words', 'max_words'):
        _need(core['contract'][field] == request['limits'][field])
    plan = core['plan']
    selected = plan['fact_ids']
    _need(type(selected) is list and 1 <= len(selected) <= 4)
    _need(type(plan['required_ids']) is list and len(plan['required_ids']) == len(selected)
          and set(plan['required_ids']) == set(selected) and len(set(selected)) == len(selected))
    _need(type(core['facts']) is list and type(core['sources']) is list)
    facts = {f['id']: f for f in core['facts']}
    chosen = [facts[item] for item in selected]
    _need(len({fact['subject'] for fact in chosen}) == 1)
    used = {fact['source_id'] for fact in chosen}
    _need(used <= set(request['dossier']['necessary_source_ids']))
    core_sources = {s['id']: s for s in core['sources']}
    host_sources = {s['id']: s for s in request['sources']}
    for sid in used:
        _need(all(core_sources[sid][key] == host_sources[sid][key]
                  for key in ('id', 'workspace', 'version', 'sha256', 'state')))


def _prepare(request, revision):
    status = request['dossier']['status']
    if status != 'supported':
        decision = 'review_required' if status == 'not_reviewed' else status
        return decision, _NOTICES[decision], []
    try:
        _compatible(request)
        # C1 rechecks its bindings and mechanics. Live authority belongs to the
        # enclosing before/before_handoff observations, not this fixed callback.
        rendered = _c1.render(request['c1_request'],
                              lambda snapshot, stage: {'status': 'allowed', 'revision': revision})
        if rendered['status'] == 'ok':
            return 'admitted', rendered['body'], rendered['provenance']
        if rendered['status'] == 'ambiguous':
            return 'conflict', _NOTICES['conflict'], []
    except Exception:
        pass
    return 'output_constraint', '', []


def _mechanical(body, limits, citations):
    try:
        contract = _counter.OutputContract(limits['min_words'], limits['max_words'],
                                            'fr', tuple(citations))
        return _counter.validate_output(body, contract)['mechanical_pass'] is True
    except Exception:
        return False


def _terminal(request_id, decision, body, review, revision, provenance, limits, citations):
    """Construct final objects from scratch. No raw C1 state reaches this layer."""
    if decision in _ACCESS:
        review, revision, provenance = 'not_disclosed', None, []
        body = _NOTICES[decision]
    cause = None
    if body and not _mechanical(body, limits, citations if decision == 'admitted' else ()):
        cause, decision, body, provenance = decision, 'output_constraint', '', []
    if decision != 'admitted':
        provenance = []
    envelope = {'decision': decision,
                'body_kind': ('technical_card' if decision == 'admitted' else 'notice') if body else 'none',
                'body': body, 'body_sha256': _sha(body.encode('utf-8')) if body else None,
                'request_id': request_id, 'contract_revision': 'admission-r2',
                'authority_revision': revision, 'evidence_review': review,
                'consumer_verified': bool(body), 'publication_atomic': False}
    receipt = {'request_id': request_id, 'decision': decision, 'cause': cause,
               'evidence_review': review, 'authority_revision': revision,
               'provenance': _clone(provenance), 'publication_atomic': False,
               'extraction_measured': False}
    return {'envelope': envelope, 'receipt': receipt,
            'handoff': {'attempted': 0, 'delivery': 'not_attempted', 'incident': None}}


def _handoff(result, sink):
    if not result['envelope']['body']:
        return result
    # Set the observable attempt before any consumer-controlled effect.
    result['handoff']['attempted'] = 1
    try:
        ack = sink(_clone(result['envelope']), _clone(result['receipt']))
    except Exception:
        result['handoff'].update(delivery='unknown', incident='sink_exception')
        result['envelope']['consumer_verified'] = False
        return result
    try:
        _fields(ack, {'status', 'body_sha256'})
        _need(type(ack['status']) is str and ack['status'] == 'received')
        _need(type(ack['body_sha256']) is str and _HASH.fullmatch(ack['body_sha256']) is not None)
    except Exception:
        result['handoff'].update(delivery='unknown', incident='sink_ack_invalid')
        result['envelope']['consumer_verified'] = False
        return result
    if ack['body_sha256'] != result['envelope']['body_sha256']:
        result['handoff'].update(delivery='unknown', incident='sink_hash_mismatch')
        result['envelope']['consumer_verified'] = False
    else:
        result['handoff']['delivery'] = 'acknowledged'
    return result


class LabOrchestratorSink:
    """Observable lab consumer. Recording happens only at the handoff boundary."""

    def __init__(self):
        self.calls = 0
        self.received = []

    def __call__(self, envelope, receipt):
        self.calls += 1
        self.received.append(_clone({'envelope': envelope, 'receipt': receipt}))
        return {'status': 'received', 'body_sha256': envelope['body_sha256']}


def admit(request, authority, sink, transform=None):
    """Trusted reviewed dossier -> controlled handoff. No semantic inference."""
    request_id = uuid.uuid4().hex
    fallback_limits = {'min_words': 1, 'max_words': 10000}
    try:
        captured, necessary = _request(request)
    except Exception:
        return _terminal(request_id, 'invalid_request', '', 'not_checked', None, [],
                         fallback_limits, ())
    limits = dict(captured['limits'])
    if not captured['accepts_format']:
        result = _terminal(request_id, 'unsupported_intent', _NOTICES['unsupported_intent'],
                           'not_checked', None, [], limits, ())
        captured.clear()
        necessary.clear()
        return _handoff(result, sink)
    if any(source['workspace'] != captured['workspace'] for source in necessary):
        decision, revision = 'access_unavailable', None
    else:
        decision, revision = _authority(authority, captured['workspace'], necessary, 'before')
        if decision is None and any(source['state'] == 'revoked' for source in necessary):
            decision, revision = 'access_unavailable', None
    if decision is not None:
        result = _terminal(request_id, decision, '', 'not_disclosed', None, [], limits, ())
        captured.clear()
        necessary.clear()
        return _handoff(result, sink)
    decision, body, provenance = _prepare(captured, revision)
    review = 'conflict' if decision == 'conflict' else captured['dossier']['status']
    mismatch = False
    if body and transform is not None:
        raw = body.encode('utf-8')
        try:
            transformed = transform(raw)
            mismatch = not (type(transformed) is bytes and len(transformed) <= 65536
                            and transformed == raw)
        except Exception:
            mismatch = True
        finally:
            raw = transformed = None
    final_decision, final_revision = _authority(authority, captured['workspace'], necessary,
                                               'before_handoff')
    if final_decision is None and final_revision != revision:
        final_decision = 'authority_changed'
    citations = ()
    if final_decision is not None:
        decision, body, provenance, review, revision = final_decision, '', [], 'not_disclosed', None
    elif mismatch:
        decision, body, provenance = 'consumer_changed', '', []
    elif decision == 'admitted':
        citations = tuple(item['source_id'] for item in provenance)
        citations = tuple(dict.fromkeys(citations))
    # Drop preparation references before building or invoking any consumer.
    captured.clear()
    necessary.clear()
    result = _terminal(request_id, decision, body, review, revision, provenance, limits, citations)
    body, provenance, citations = '', [], ()
    return _handoff(result, sink)
