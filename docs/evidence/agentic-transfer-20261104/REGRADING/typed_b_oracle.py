"""Pinned pure grading functions for synthetic B artifacts."""

import ast
import csv
import hashlib
import io
import json


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def invalid_response():
    # No artifact exists for this observed terminal response. Do not invent
    # artifact bytes or select an earlier success to pass the private oracle.
    return {'oracle_status': 'KNOWN', 'business_passed': False,
            'typed_semantics': False, 'exact_bytes': False, 'artifact_sha256': None,
            'reason': 'invalid_generated_artifact',
            'failure_kind': 'invalid_terminal_response'}


def coder_record(content, ordinal):
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        value = None
    valid = (type(value) is dict and set(value) == {'code', 'filename'}
             and type(value['code']) is str and type(value['filename']) is str)
    return {'attempt': ordinal,
            'code': value['code'] if valid and value['code'].strip() else None,
            'filename': value['filename'] if valid else None,
            'return_sha256': sha(content.encode())}


def artifact_verdict(case, record, oracle):
    verdict = {'oracle_status': 'KNOWN', **oracle(case, record['code'].encode())}
    if record['filename'] != 'main.py':
        verdict.update(business_passed=False, reason='unexpected_artifact_filename',
                       expected_filename='main.py', actual_filename=record['filename'])
    return verdict


RULES = {'B.inclusive': 'Eligible when value >= threshold.',
         'B.exclusive': 'Eligible when value > threshold.'}


def _typed_equal(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(_typed_equal(actual[k], expected[k]) for k in expected)
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_typed_equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


def expected_eligible(data, convention):
    """Same threshold reference as fixture_contract.expected_business family B."""
    if convention not in RULES or type(data['threshold']) is not int:
        raise ValueError('unsupported_native_threshold')
    return [value >= data['threshold'] if convention == 'B.inclusive' else value > data['threshold']
            for value in data['values']]


def literal_result(raw):
    """Existing inert single-RESULT grammar; never execute generated Python."""
    if type(raw) is not str or not 0 < len(raw.encode()) <= 24000:
        raise ValueError('artifact_bound')
    tree = ast.parse(raw)
    if (len(tree.body) != 1 or type(tree.body[0]) is not ast.Assign
            or len(tree.body[0].targets) != 1 or type(tree.body[0].targets[0]) is not ast.Name
            or tree.body[0].targets[0].id != 'RESULT'):
        raise ValueError('inert_RESULT_required')
    value = ast.literal_eval(tree.body[0].value)
    if type(value) is not dict:
        raise ValueError('RESULT_not_dict')
    return value


def business_b_oracle(host_only_case, artifact):
    """Existing typed CSV comparison; B case is never present in A bundle."""
    try:
        value = literal_result(artifact.decode('utf-8'))
        if set(value) != {'retained_csv'} or type(value['retained_csv']) is not str:
            raise ValueError('B_retained_csv_required')
        actual = value['retained_csv'].encode('utf-8')
        rows = list(csv.reader(io.StringIO(value['retained_csv'], newline=''), delimiter=';'))
        expected = [host_only_case['columns'], *host_only_case['rows']]
        stream = io.StringIO(newline='')
        writer = csv.writer(stream, delimiter=';', lineterminator='\r\n')
        writer.writerows(expected)
        wanted = stream.getvalue().encode('utf-8')
        return {'business_passed': _typed_equal(rows, expected), 'typed_semantics': _typed_equal(rows, expected),
                'exact_bytes': actual == wanted, 'artifact_sha256': sha(artifact),
                'business_bytes_sha256': sha(actual)}
    except (ValueError, TypeError, KeyError, SyntaxError, UnicodeError, csv.Error):
        return {'business_passed': False, 'typed_semantics': False, 'exact_bytes': False,
                'artifact_sha256': sha(artifact), 'reason': 'invalid_generated_artifact'}
