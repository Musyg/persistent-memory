"""Finite structured-fact rendering, with no extraction or semantic truth claim."""
from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import re
import sys
import unicodedata

COUNTER_SHA256 = '0d16ebbf0042f03a5d6b36b1ed3b32b58e00945b73af1582f4bf2760492123b4'
_counter_path = Path(__file__).resolve().with_name('quality_contract.py')
_counter_bytes = _counter_path.read_bytes()
if hashlib.sha256(_counter_bytes).hexdigest() != COUNTER_SHA256:
    raise ImportError('historical_mechanical_validator_pin_mismatch')
_counter_name = '_hermes_c1_pinned_mechanical'
_spec = importlib.util.spec_from_file_location(_counter_name, _counter_path)
_counter = importlib.util.module_from_spec(_spec)
sys.modules[_counter_name] = _counter
# Execute the bytes already checked; avoid a second unpinned source read.
exec(compile(_counter_bytes, str(_counter_path), 'exec'), _counter.__dict__)

_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_NUMBER = re.compile(r'-?(0|[1-9][0-9]*)(\.[0-9]+)?\Z')
_SOURCE_FIELDS = {'id','workspace','version','sha256','text','state'}
_FACT_FIELDS = {'id','subject','property','value','unit','polarity','scope','cardinality',
                'source_id','source_version','source_sha256','span','origin','certainty'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


class _Reject(Exception):
    def __init__(self, status, reason):
        self.status, self.reason = status, reason


def _need(condition, reason, status='invalid_request'):
    if not condition:
        raise _Reject(status, reason)


def _fields(value, names, label):
    _need(type(value) is dict and len(value) == len(names)
          and all(type(key) is str for key in value) and set(value) == names, label+'_fields')


def _identifier(value, label):
    _need(type(value) is str and _ID.fullmatch(value) is not None, label+'_identifier')


def _hash(value, label):
    _need(type(value) is str and _SHA.fullmatch(value) is not None, label+'_hash')


def _literal(value, maximum, label, *, empty=False):
    _need(type(value) is str and len(value) <= maximum, label+'_string')
    _need((empty or bool(value)) and value == value.strip() and '  ' not in value,
          label+'_spacing')
    _need(not any(c in '[]«»' or unicodedata.category(c).startswith('C')
                  or (c.isspace() and c != ' ') for c in value), label+'_characters')


def _bounded_json_size(value, maximum=262144):
    """Count exact canonical JSON UTF-8 size without materializing the document.

    Basic schema/types/collection bounds have already been checked. String scans
    stop at the remaining byte budget; integer conversion gets a conservative
    bit-length guard first. This function never normalizes caller types.
    """
    size = 0
    def add(amount):
        nonlocal size
        size += amount
        _need(size <= maximum, 'request_byte_bound')
    def string(text):
        _need(type(text) is str and len(text) <= maximum-size, 'request_byte_bound')
        add(2)
        for char in text:
            point = ord(char)
            _need(not 0xD800 <= point <= 0xDFFF, 'request_unicode')
            if char in '"\\\b\f\n\r\t': add(2)
            elif point < 0x20: add(6)
            elif point < 0x80: add(1)
            elif point < 0x800: add(2)
            elif point < 0x10000: add(3)
            else: add(4)
    def visit(item):
        if type(item) is str:
            string(item)
        elif type(item) is bool:
            add(4 if item else 5)
        elif type(item) is int:
            # Every decimal digit needs fewer than four bits; rejection here
            # cannot exclude an integer whose JSON fits the remaining budget.
            _need(item.bit_length() <= 4*(maximum-size), 'request_integer_bound')
            try: digits = str(item)
            except ValueError: raise _Reject('invalid_request','request_integer_encoding') from None
            add(len(digits))
        elif type(item) is list:
            add(2+max(0,len(item)-1))
            for child in item: visit(child)
        elif type(item) is dict:
            add(2+max(0,len(item)-1))
            for key,child in item.items():
                string(key)
                add(1)
                visit(child)
        else:
            raise _Reject('invalid_request','request_json_type')
    visit(value)
    return size


def _basic(request):
    _fields(request, {'schema','workspace','sources','facts','plan','contract'}, 'request')
    _need(type(request['schema']) is str and request['schema'] == 'hermes.structured.request.v1', 'request_schema')
    _identifier(request['workspace'], 'workspace')
    sources, facts = request['sources'], request['facts']
    _need(type(sources) is list and len(sources) <= 16, 'sources_bound')
    _need(type(facts) is list and len(facts) <= 32, 'facts_bound')
    for source in sources:
        _fields(source, _SOURCE_FIELDS, 'source')
        for key in ('id','workspace','version'): _identifier(source[key], 'source_'+key)
        _hash(source['sha256'], 'source')
        _need(type(source['text']) is str and len(source['text']) <= 16384, 'source_text')
        try: source_size = len(source['text'].encode('utf-8'))
        except UnicodeError: raise _Reject('invalid_request','source_unicode') from None
        _need(source_size <= 16384, 'source_text')
        _need(type(source['state']) is str and source['state'] in ('active','revoked'), 'source_state')
    _need(len({s['id'] for s in sources}) == len(sources), 'duplicate_source_id')
    for fact in facts:
        _fields(fact, _FACT_FIELDS, 'fact')
        for key in ('id','source_id','source_version'): _identifier(fact[key], 'fact_'+key)
        _hash(fact['source_sha256'], 'fact_source')
        for key in ('subject','property','scope'): _literal(fact[key], 80, key)
        _literal(fact['unit'], 40, 'unit', empty=True)
        _fields(fact['value'], {'type','value'}, 'value')
        _need(type(fact['value']['type']) is str, 'value_type')
        _literal(fact['value']['value'], 160, 'value')
        _need(type(fact['cardinality']) is str, 'cardinality_type')
        _need(type(fact['polarity']) is str and fact['polarity'] in ('positive','negative'), 'polarity')
        _need(type(fact['origin']) is str and fact['origin'] in ('document','brief_fact','instruction'), 'origin')
        _need(type(fact['certainty']) is str and fact['certainty'] in ('asserted','ambiguous'), 'certainty')
        _fields(fact['span'], {'start','end','text'}, 'span')
        _need(type(fact['span']['start']) is int and type(fact['span']['end']) is int
              and type(fact['span']['text']) is str, 'span_types')
        # An unused span is not rebound or semantically validated. Its text
        # still cannot be larger than the entire request's UTF-8 budget.
        _need(len(fact['span']['text']) <= 262144, 'span_text_bound')
    _need(len({f['id'] for f in facts}) == len(facts), 'duplicate_fact_id')
    _fields(request['plan'], {'fact_ids','required_ids'}, 'plan')
    ids, required = request['plan']['fact_ids'], request['plan']['required_ids']
    for values in (ids, required):
        _need(type(values) is list and 1 <= len(values) <= 8, 'plan_bound')
        for value in values: _identifier(value, 'plan_fact')
        _need(len(set(values)) == len(values), 'plan_duplicate')
    _need(set(required) <= set(ids), 'required_not_selected')
    _need(set(ids) <= {f['id'] for f in facts}, 'unknown_selected_fact')
    contract = request['contract']
    _fields(contract, {'language','min_words','max_words','max_candidates','allow_repair'}, 'contract')
    _need(type(contract['language']) is str, 'language_type')
    _need(contract['language'] == 'fr', 'language_not_supported', 'unsupported_scope')
    for key in ('min_words','max_words','max_candidates'):
        _need(type(contract[key]) is int, key+'_integer')
    _need(1 <= contract['min_words'] <= contract['max_words'] <= 10000, 'word_bounds')
    _need(1 <= contract['max_candidates'] <= 64, 'candidate_bound')
    _need(type(contract['allow_repair']) is bool, 'repair_boolean')
    by_id = {f['id']:f for f in facts}
    return [by_id[i] for i in ids], {s['id']:s for s in sources}


def _selected(request, facts, sources):
    claims, groups = set(), {}
    for fact in facts:
        _need(fact['origin'] != 'instruction', 'instruction_selected', 'unsupported_scope')
        _need(fact['cardinality'] == 'single', 'cardinality_not_supported', 'unsupported_scope')
        kind, value = fact['value']['type'], fact['value']['value']
        _need(kind in ('text','number'), 'value_type_not_supported', 'unsupported_scope')
        if kind == 'number':
            _need(len(value) <= 40 and _NUMBER.fullmatch(value) is not None, 'number_lexical_form')
        else:
            _need(fact['unit'] == '', 'text_with_unit')
        _need(fact['certainty'] == 'asserted', 'ambiguous_selected_fact', 'ambiguous')
        _need(fact['source_id'] in sources, 'missing_source')
        source = sources[fact['source_id']]
        _need(source['workspace'] == request['workspace'], 'foreign_workspace', 'unsupported_scope')
        _need(source['state'] == 'active', 'declared_revoked_source', 'revoked')
        _need(_digest(source['text'].encode('utf-8')) == source['sha256'], 'source_content_hash')
        _need(fact['source_sha256'] == source['sha256'] and fact['source_version'] == source['version'],
              'source_version_binding')
        span = fact['span']
        _need(0 <= span['start'] < span['end'] <= len(source['text'])
              and source['text'][span['start']:span['end']] == span['text'], 'source_span_binding')
        group = (fact['subject'], fact['property'], fact['scope'])
        typed_value = (kind, value, fact['unit'])
        claim = (group, typed_value, fact['polarity'])
        _need(claim not in claims, 'duplicate_claim')
        claims.add(claim)
        groups.setdefault(group, []).append((typed_value,fact['polarity']))
    for members in groups.values():
        positives = {value for value,polarity in members if polarity == 'positive'}
        negatives = {value for value,polarity in members if polarity == 'negative'}
        _need(len(positives) <= 1 and not positives.intersection(negatives),
              'single_valued_conflict', 'ambiguous')


def _sentence(fact, variant):
    subject, prop, scope = fact['subject'], fact['property'], fact['scope']
    value = fact['value']['value']
    if fact['value']['type'] == 'text': value = '« '+value+' »'
    unit = ' unité « '+fact['unit']+' »' if fact['unit'] else ''
    citation = ' ['+fact['source_id']+']'
    positive = fact['polarity'] == 'positive'
    if variant == 'compact':
        operator = '=' if positive else '≠'
        return f'« {subject} » : « {prop} » {operator} {value}{unit} ; portée « {scope} ».'+citation
    verb = 'a pour valeur' if positive else "n'a pas pour valeur"
    return f'Pour la portée « {scope} », la propriété « {prop} » de « {subject} » {verb} {value}{unit}.'+citation


def _body(facts, variants):
    sentences, provenance, used = [], [], []
    cursor = 0
    for fact, variant in zip(facts, variants):
        if variant == 'omitted': continue
        sentence = _sentence(fact, variant)
        if sentences: cursor += 1
        provenance.append({'fact_id':fact['id'],'fact_sha256':_digest(canonical(fact)),
            'source_id':fact['source_id'],'source_version':fact['source_version'],
            'source_sha256':fact['source_sha256'],'span':dict(fact['span']),
            'start':cursor,'end':cursor+len(sentence),'segment_sha256':_digest(sentence.encode('utf-8'))})
        sentences.append(sentence)
        used.append(fact['id'])
        cursor += len(sentence)
    return ' '.join(sentences), provenance, used


def _authority(authority, snapshot, stage, checks):
    reason = None
    try:
        response = authority(json.loads(canonical(snapshot)), stage)
        _fields(response, {'status','revision'}, 'authority_response')
        status, revision = response['status'], response['revision']
        _need(type(status) is str and status in ('allowed','revoked','unavailable'), 'authority_status')
        if status == 'unavailable': _need(revision is None, 'authority_unavailable_revision')
        else: _identifier(revision, 'authority_revision')
    except Exception:
        status, revision, reason = 'unavailable', None, 'callback_error_or_invalid_response'
    checks.append({'stage':stage,'status':status,'revision':revision,'reason':reason})
    _need(status != 'unavailable', 'authority_unavailable', 'authority_unavailable')
    _need(status != 'revoked', 'authority_revoked', 'revoked')
    return revision


def render(request, authority):
    """Render explicitly supplied facts. A success is mechanical, not semantic."""
    result = {'schema':'hermes.structured.result.v1','status':'invalid_request','reason':None,
      'body':'','request_sha256':None,'word_count':None,'fact_ids':[],
      'coverage':{'required_ids':[],'rendered_ids':[],'omitted_optional_ids':[],'missing_required_ids':[]},
      'provenance':[],'attempts':[],'authority_checks':[], 'semantic_status':'not_evaluated',
      'publication_atomic':False,'repair_transactions':0}
    try:
        _need(type(request) is dict, 'request_object')
        # Check the original Python types and bounded shape before JSON can
        # normalize tuples/subclasses or allocate a complete serialized copy.
        _basic(request)
        measured_size = _bounded_json_size(request)
        try: encoded = canonical(request)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise _Reject('invalid_request','request_json') from None
        _need(len(encoded) <= 262144, 'request_byte_bound')
        _need(len(encoded) == measured_size, 'request_changed_during_capture')
        captured = json.loads(encoded)
        result['request_sha256'] = _digest(encoded)
        facts, sources = _basic(captured)
        required = captured['plan']['required_ids']
        result['coverage']['required_ids'] = list(required)
        result['coverage']['missing_required_ids'] = list(required)
        _selected(captured, facts, sources)
        source_ids = sorted({f['source_id'] for f in facts})
        snapshot = {'workspace':captured['workspace'],'request_sha256':result['request_sha256'],
                    'sources':[{k:sources[i][k] for k in ('id','version','sha256')} for i in source_ids]}
        revision = _authority(authority, snapshot, 'before', result['authority_checks'])
        contract = captured['contract']
        mechanical_contract = _counter.OutputContract(contract['min_words'],contract['max_words'],
                                                        'fr',tuple(source_ids))
        choices = [('compact','expanded') if f['id'] in required else ('compact','expanded','omitted')
                   for f in facts]
        total = 1
        for choice in choices: total *= len(choice)
        if not contract['allow_repair']: total = 1
        limit = min(total,contract['max_candidates'])
        for index, variants in enumerate(itertools.islice(itertools.product(*choices),limit),1):
            body, provenance, used = _body(facts,variants)
            check = _counter.validate_output(body,mechanical_contract)
            result['repair_transactions'] = int(index > 1)
            result['attempts'].append({'index':index,'variants':list(variants),
                'word_count':check['word_count'],'mechanical_pass':check['mechanical_pass'],'errors':check['errors']})
            if check['mechanical_pass']:
                after = _authority(authority,snapshot,'after',result['authority_checks'])
                _need(after == revision, 'authority_revision_changed', 'authority_changed')
                result.update(status='ok',reason=None,body=body,word_count=check['word_count'],
                              fact_ids=used,provenance=provenance)
                result['coverage'].update(rendered_ids=used,missing_required_ids=[],
                    omitted_optional_ids=[f['id'] for f in facts if f['id'] not in used])
                return result
        result['status'] = 'search_limit_reached' if limit < total else 'constraint_unsatisfied'
        result['reason'] = 'bounded_finite_rendering_exhausted' if limit == total else 'candidate_bound_reached'
    except _Reject as error:
        result['status'],result['reason'] = error.status,error.reason
    return result
