"""Pure synthetic XP fixture/projection/oracle contract. No I/O at import.

This independent reference never imports the consumer, Memory, providers or a
runner. expected_business and full cases are HOST ONLY. Public source contains
rules and algorithms, never sealed B values. Runtime fresh-file reads belong to
the existing isolated verifier, which passes the actual bytes to these functions.
"""
import base64
import copy
import csv
import hashlib
import io
import json


CONVENTIONS = {
    'I': {'I.opaque': 'Preserve each ASCII digit identifier verbatim.',
          'I.numeric': 'Normalize each identifier as decimal str(int(identifier, 10)).'},
    'B': {'B.inclusive': 'Eligible when value >= threshold.',
          'B.exclusive': 'Eligible when value > threshold.'},
    'S': {'S.debit_negative': 'Debit amounts negative; credit amounts positive.',
          'S.debit_positive': 'Debit amounts positive; credit amounts negative.'},
    'T': {'T.primary': 'Higher revision wins; at equal revision primary wins.',
          'T.secondary': 'Higher revision wins; at equal revision secondary wins.'},
    'C': {'C.bom': 'Receiver accepts UTF-8 CSV with leading BOM.',
          'C.plain': 'Receiver accepts UTF-8 CSV without BOM.'},
    'R': {'R.signed': 'Approval equals the signed boolean.',
          'R.sealed': 'Approval equals the sealed boolean.'},
}
CANDIDATE_IDS = frozenset(k for rules in CONVENTIONS.values() for k in rules)
TARGETS = {'I': {'A': 'import.json', 'B': 'deduplicated.csv'},
           'B': {'A': 'eligibility.json', 'B': 'retained.csv'},
           'S': {'A': 'ledger.json', 'B': 'consolidated.csv'},
           'T': {'A': 'catalog.json', 'B': 'conflicts.json'},
           'C': {'A': 'probe.csv', 'B': 'rejected.csv'},
           'R': {'A': 'release.json', 'B': 'archive.json'}}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_artifact(value):
    return (canonical(value) + '\n').encode('utf-8'), {'kind': 'json', 'value': value}


def csv_artifact(columns, rows, delimiter, encoding):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, delimiter=delimiter, lineterminator='\r\n')
    writer.writerow(columns)
    writer.writerows(rows)
    return stream.getvalue().encode(encoding), {'kind': 'csv', 'columns': columns,
            'rows': rows, 'delimiter': delimiter, 'encoding': encoding}


def blob(raw):
    return {'base64': base64.b64encode(raw).decode('ascii'), 'sha256': sha(raw)}


def _identifier(value, numeric):
    if type(value) is not str or not value or any(c not in '0123456789' for c in value):
        raise ValueError('identifier must contain ASCII digits only')
    return str(int(value, 10)) if numeric else value


def _signed(entry, convention):
    if entry['kind'] not in ('debit', 'credit') or type(entry['magnitude']) is not int or entry['magnitude'] <= 0:
        raise ValueError('positive integer magnitude and documented ledger kind required')
    negative = (entry['kind'] == 'debit') == (convention == 'S.debit_negative')
    return -entry['magnitude'] if negative else entry['magnitude']


def _winner(primary, secondary, convention):
    if primary is None:
        return 'secondary', secondary, False
    if secondary is None:
        return 'primary', primary, False
    if primary['key'] != secondary['key']:
        raise ValueError('winner inputs must share key')
    tied = primary['revision'] == secondary['revision']
    side = ('primary' if convention == 'T.primary' else 'secondary') if tied else (
           'primary' if primary['revision'] > secondary['revision'] else 'secondary')
    return side, primary if side == 'primary' else secondary, tied


def expected_business(family, phase, data, convention_id):
    """HOST ONLY: independently derive one expected business artifact."""
    if family not in CONVENTIONS or phase not in ('A', 'B') or convention_id not in CONVENTIONS[family]:
        raise ValueError('unknown family, phase or convention')
    target = TARGETS[family][phase]
    if family == 'I':
        numeric = convention_id == 'I.numeric'
        if phase == 'A':
            value = {'identifiers': [_identifier(x, numeric) for x in data['identifiers']]}
        else:
            seen, rows = set(), []
            for row in data['rows']:
                ident = _identifier(row['identifier'], numeric)
                if ident not in seen:
                    rows.append([ident, row['label']]); seen.add(ident)
            raw, fmt = csv_artifact(data['csv']['columns'], rows, data['csv']['delimiter'], data['csv']['encoding'])
            return target, raw, fmt
    elif family == 'B':
        def eligible(value):
            return value >= data['threshold'] if convention_id == 'B.inclusive' else value > data['threshold']
        if phase == 'A':
            value = {'eligible': [eligible(x) for x in data['values']]}
        else:
            rows = [[r['record_id'], str(r['value'])] for r in data['rows'] if eligible(r['value'])]
            raw, fmt = csv_artifact(data['csv']['columns'], rows, data['csv']['delimiter'], data['csv']['encoding'])
            return target, raw, fmt
    elif family == 'S':
        if phase == 'A':
            value = {'amounts': [_signed(e, convention_id) for e in data['entries']]}
        else:
            totals = {}
            for entry in data['entries']:
                account = entry['account']
                totals[account] = totals.get(account, 0) + _signed(entry, convention_id)
            rows = [[account, str(net)] for account, net in totals.items()]
            raw, fmt = csv_artifact(data['csv']['columns'], rows, data['csv']['delimiter'], data['csv']['encoding'])
            return target, raw, fmt
    elif family == 'T':
        if phase == 'A':
            _, retained, _ = _winner(data['primary'], data['secondary'], convention_id)
            value = {'retained': retained}
        else:
            primary = {r['key']: r for r in data['primary']}
            secondary = {r['key']: r for r in data['secondary']}
            if len(primary) != len(data['primary']) or len(secondary) != len(data['secondary']):
                raise ValueError('duplicate key within one input')
            keys = list(primary) + [k for k in secondary if k not in primary]
            decisions = []
            for key in keys:
                side, _, tied = _winner(primary.get(key), secondary.get(key), convention_id)
                decisions.append({'key': key, 'winner_source': side, 'equal_revision': tied})
            value = {'decisions': decisions, 'tie_count': sum(d['equal_revision'] for d in decisions)}
    elif family == 'C':
        encoding = 'utf-8-sig' if convention_id == 'C.bom' else 'utf-8'
        rows = data['rows'] if phase == 'A' else [[r['record_id'], r['issue']] for r in data['records'] if r['status'] == 'rejected']
        raw, fmt = csv_artifact(data['csv']['columns'], rows, data['csv']['delimiter'], encoding)
        return target, raw, fmt
    else:
        field = 'signed' if convention_id == 'R.signed' else 'sealed'
        if phase == 'A':
            value = {'approved': data['record'][field]}
        else:
            value = {'archive': [r['record_id'] for r in data['records'] if r[field]],
                     'held': [r['record_id'] for r in data['records'] if not r[field]]}
    raw, fmt = json_artifact(value)
    return target, raw, fmt


def project_case(case, phase):
    """No hidden receiver convention, B goal or oracle leaks into A."""
    if phase not in ('A', 'B'):
        raise ValueError('phase')
    task = copy.deepcopy(case[phase]['task'])
    target = TARGETS[case['family']][phase]
    source_id = 'authority-' + case['world_id'] + '-' + phase
    observation_id = 'observation-' + source_id
    conditions = {'receiver_scope': case['receiver_scope'], 'phase': phase}
    task['conditions'] = conditions
    task['target_dependencies'] = {'control.json': None, target: source_id}
    observation = {'observation_id': observation_id, 'source_id': source_id,
        'text': 'Receiver scope ' + case['receiver_scope'] + ' permits writing ' + target
                + '; this authority specifies no receiver convention.',
        'metadata': {'evidence_kind': 'procedure', 'observed_at': '2026-10-23T00:00:00Z',
                     'preconditions': conditions, 'aliases': [], 'confidence': None,
                     'valid_from': None, 'valid_until': None}}
    event = {'seq': 1, 'event_id': 'put-' + source_id, 'op': 'put', 'observation_id': observation_id}
    return copy.deepcopy({**{k: case[k] for k in ('world_id', 'template_id', 'workspace', 'language', 'family')},
                          'task': task, 'observations': [observation], 'events': [event]})


def get_oracle(case, phase):
    if phase not in ('A', 'B'):
        raise ValueError('phase')
    return copy.deepcopy(case[phase]['oracle'])


def feedback_from_a(case, observed_files, check_id):
    """Actual fresh business bytes only; feedback never writes the correct rule."""
    family, data = case['family'], case['A']['task']['data']
    target = TARGETS[family]['A']
    raw = observed_files.get(target)
    if raw is not None and type(raw) is not bytes:
        raise ValueError('actual observed files must be bytes or None')
    matched = [] if raw is None else [rule for rule in CONVENTIONS[family]
              if expected_business(family, 'A', data, rule)[1] == raw]
    discriminating = len(matched) == 1
    attempted = matched[0] if discriminating else None
    success = None if raw is None else raw == expected_business(family, 'A', data, case['receiver_convention'])[1]
    violation = ('artifact_unavailable' if raw is None else 'non_discriminating_witness'
                 if not discriminating else None if success else 'receiver_convention_mismatch')
    return {'schema': 'experience-feedback-v1', 'check_id': check_id,
            'receiver_scope': case['receiver_scope'], 'success': success,
            'violation_code': violation,
            'observed': {'artifact_sha256': sha(raw) if raw is not None else None,
                         'attempted_convention': attempted, 'discriminating': discriminating}}


def grade_lesson(case, candidate, trace_sha256, feedback_sha256, feedback):
    """Grade structured inference; never mutate/replace the model's lesson."""
    keys = {'schema', 'convention_id', 'scope', 'evidence_refs', 'text'}
    shape = (type(candidate) is dict and set(candidate) == keys
             and candidate.get('schema') == 'experience-procedure-v1'
             and type(candidate.get('convention_id')) is str
             and candidate['convention_id'] in CANDIDATE_IDS
             and type(candidate.get('scope')) is str
             and type(candidate.get('evidence_refs')) is list
             and len(candidate['evidence_refs']) == 2
             and all(type(x) is str for x in candidate['evidence_refs'])
             and type(candidate.get('text')) is str and 0 < len(candidate['text']) <= 1500)
    integrity = (type(feedback) is dict and feedback.get('schema') == 'experience-feedback-v1'
                 and feedback.get('receiver_scope') == case['receiver_scope']
                 and sha(canonical(feedback).encode('utf-8')) == feedback_sha256)
    refs = bool(shape and integrity and candidate['evidence_refs'] == [trace_sha256, feedback_sha256])
    scope = bool(shape and candidate['scope'] == case['receiver_scope'])
    available = bool(integrity and type(feedback.get('observed')) is dict
                     and feedback['observed'].get('discriminating') is True
                     and type(feedback.get('success')) is bool)
    choice = bool(shape and candidate['convention_id'] == case['receiver_convention']) if available else None
    valid = (bool(shape and refs and scope and choice) if available else None)
    return {'shape_valid': bool(shape), 'references_valid': refs, 'scope_valid': scope,
            'evidence_available': available, 'choice_correct': choice, 'valid': valid,
            'text_semantics_graded': False}


def _typed_equal(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return set(actual) == set(expected) and all(_typed_equal(actual[k], expected[k]) for k in expected)
    if type(expected) is list:
        return len(actual) == len(expected) and all(_typed_equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _format_ok(raw, fmt):
    try:
        if fmt['kind'] == 'json':
            return _typed_equal(json.loads(raw.decode('utf-8')), fmt['value'])
        rows = list(csv.reader(io.StringIO(raw.decode(fmt['encoding']), newline=''), delimiter=fmt['delimiter']))
        return rows == [fmt['columns'], *fmt['rows']]
    except (ValueError, UnicodeError, KeyError, TypeError, csv.Error):
        return False


def verify_oracle(oracle, observed_files, *, cell_id=None):
    """Pure independent oracle over fresh bytes supplied by the host verifier."""
    expected = copy.deepcopy(oracle['expected_files'])
    if cell_id is not None:
        raw, fmt = json_artifact({'cell_id': cell_id, 'completed': True})
        expected[oracle['control']['target']] = {**blob(raw), 'format': fmt}
    checks = {}
    for target, spec in expected.items():
        want = base64.b64decode(spec['base64'], validate=True)
        if sha(want) != spec['sha256']:
            raise ValueError('invalid expected-file hash')
        raw = observed_files.get(target)
        checks[target] = {'exact_bytes': type(raw) is bytes and raw == want,
                          'typed_semantics': type(raw) is bytes and _format_ok(raw, spec['format'])}
    for target, pin in oracle['unchanged_files'].items():
        raw = observed_files.get(target)
        checks[target] = {'unchanged': type(raw) is bytes and sha(raw) == pin}
    allowed = set(expected) | set(oracle['unchanged_files'])
    if cell_id is None:
        allowed.add(oracle['control']['target'])
    checks['inventory'] = {'no_extra_files': set(observed_files) <= allowed}
    return {'passed': all(all(c.values()) for c in checks.values()), 'checks': checks}
