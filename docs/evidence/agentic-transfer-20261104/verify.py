"""Verify and reduce the public CONF projection without a model or runtime data."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


MODULE_PINS = {
    'reduce_conf_grades.py': '49068c54fc124e1b8548468d70780ef7b7109640e7acd4e33e9dd724e91d7e8f',
    'comparative_statistics.py': 'b20b853d2b1b330d59db3186a3b47a2b5391457a78a21192cefea159b439f059',
}
ARMS = ('H', 'E', 'T', 'N')
WORLDS = {f'W{i:02d}' for i in range(1, 33)}
RESOURCE_KEYS = (
    'phase_operations', 'reserved_generations', 'wire_generations', 'model_tool_calls',
    'charged_input_tokens', 'charged_output_tokens', 'observed_input_tokens',
    'observed_output_tokens', 'observed_model_wall_ms', 'external_provider_calls',
)
ROW_KEYS = {
    'world', 'arm', 'case_join_sha256', 'gate', 'terminal', 'pipeline', 'reason_code',
    'business_passed', 'first_attempt_business_passed', 'coder_attempts', 'experience_status',
    'Y_business_ITT', 'Z_pipeline_complete', 'resources',
}
REASONS = ('GRADED', 'KNOWN_NONDELIVERY', 'UNRESOLVED', 'NOT_RUN', 'RIGHTS_OR_INTEGRITY')
EXPERIENCE = ('OBSERVED_CONTEXT', 'KNOWN_EMPTY', 'UNKNOWN', 'NOT_APPLICABLE', 'NOT_RUN')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique(pairs):
    data = dict(pairs)
    require(len(data) == len(pairs), 'duplicate JSON field')
    return data


def reject_constant(value):
    raise ValueError('invalid JSON constant: ' + value)


def load(path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique, parse_constant=reject_constant)


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact(value, fields, label):
    require(type(value) is dict and set(value) == set(fields), label + ' fields')


def resources(data, phase_cap):
    exact(data, RESOURCE_KEYS, 'resources')
    require(all(v is None or type(v) is int and v >= 0 for v in data.values()), 'resource value')
    operations = data['phase_operations']
    require(operations is None or operations <= phase_cap, 'phase operation cap')
    reserved, wire = data['reserved_generations'], data['wire_generations']
    require(reserved is None or wire is None or wire <= reserved, 'wire exceeds reservations')
    return data


def totals(resource_rows):
    result = {}
    for field in RESOURCE_KEYS:
        known = [row[field] for row in resource_rows if row[field] is not None]
        result[field] = {'known_rows': len(known), 'planned_rows': len(resource_rows),
                         'sum_known': sum(known) if known else None}
    return result


def projection(bundle, reduce_conf_grades):
    source = load(bundle / 'ROSTER.json')
    exact(source, ('schema', 'worlds'), 'roster')
    require(source['schema'] == 'persistent-memory.conf-roster.v1', 'roster schema')
    require(type(source['worlds']) is list and len(source['worlds']) == 32, 'roster size')
    roster, shared = {}, []
    for row in source['worlds']:
        exact(row, ('world', 'cohort', 'stratum', 'case_join_sha256', 'shared_A'), 'world')
        world, cohort, stratum = (row[key] for key in ('world', 'cohort', 'stratum'))
        require(world in WORLDS and world not in roster, 'duplicate or unknown public world')
        require(cohort in ('positive', 'negative') and stratum in ('admission', 'stock'), 'world cell')
        identity = {'schema': 'persistent-memory.conf-public-join.v1', 'world': world,
                    'cohort': cohort, 'stratum': stratum}
        join = sha(canonical(identity))
        require(row['case_join_sha256'] == join, 'public world join')
        roster[world] = {'cohort': cohort, 'stratum': stratum, 'request_sha256': join}
        shared.append(resources(row['shared_A'], 6))

    source = load(bundle / 'ARMS.json')
    exact(source, ('schema', 'rows'), 'results')
    require(source['schema'] == 'persistent-memory.conf-arms.v1', 'results schema')
    require(type(source['rows']) is list and len(source['rows']) == 128, 'results size')
    keyed, normalized = {}, []
    for row in source['rows']:
        exact(row, ROW_KEYS, 'world arm')
        world, arm = row['world'], row['arm']
        key = (world, arm)
        require(world in roster and arm in ARMS and key not in keyed, 'world/arm grid identity')
        join = roster[world]['request_sha256']
        require(row['case_join_sha256'] == join, 'arm join differs from roster')
        require(row['reason_code'] in REASONS and row['experience_status'] in EXPERIENCE, 'status code')
        if row['reason_code'] != 'RIGHTS_OR_INTEGRITY':
            require(row['reason_code'] in {'GRADED': ('GRADED',), 'NONDELIVERY': ('KNOWN_NONDELIVERY',),
                    'UNRESOLVED': ('UNRESOLVED', 'NOT_RUN')}.get(row['terminal'], ()), 'terminal reason')
        else:
            require(row['gate'] != 'VALID', 'rights/integrity reason conflicts with gate')
        first, attempts = row['first_attempt_business_passed'], row['coder_attempts']
        require(first is None or type(first) is bool, 'first attempt status')
        require(attempts is None or type(attempts) is int and 0 <= attempts <= 3, 'Coder attempt cap')
        if row['terminal'] == 'GRADED':
            require(type(first) is bool and attempts in (1, 2, 3), 'graded B attempt evidence')
        if row['reason_code'] == 'NOT_RUN':
            require(row['gate'] == 'UNKNOWN' and row['terminal'] == 'UNRESOLVED'
                    and row['pipeline'] == 'UNKNOWN' and row['experience_status'] == 'NOT_RUN'
                    and first is None and attempts is None, 'unrun arm must stay unknown')
        require(all(type(row[key]) is int and row[key] in (0, 1)
                    for key in ('Y_business_ITT', 'Z_pipeline_complete')), 'published binary score')
        resources(row['resources'], {'H': 7, 'E': 2, 'T': 1, 'N': 1}[arm])
        if row['reason_code'] == 'NOT_RUN':
            require(all(value in (None, 0) for value in row['resources'].values()), 'unrun arm has charges')
        keyed[key] = row
        normalized.append({'world': world, 'arm': arm, 'request_sha256': join,
                           'gate': row['gate'], 'terminal': row['terminal'],
                           'pipeline': row['pipeline'], 'reason': row['reason_code'],
                           'business_passed': row['business_passed']})

    result = reduce_conf_grades(roster, normalized)
    scores = result.pop('scores')
    for score in scores:
        row = keyed[score['world'], score['arm']]
        require(all(row[name] == score[name] for name in ('Y_business_ITT', 'Z_pipeline_complete')),
                'published score differs from pinned reducer')

    secondary = {}
    for arm in ARMS:
        rows = [row for (_, label), row in keyed.items() if label == arm]
        secondary[arm] = {
            'first_attempt_known': sum(row['first_attempt_business_passed'] is not None for row in rows),
            'first_attempt_success': sum(row['first_attempt_business_passed'] is True for row in rows),
            'terminal_known': sum(row['terminal'] != 'UNRESOLVED' for row in rows),
            'terminal_business_success': sum(row['business_passed'] is True for row in rows),
            'terminal_ITT_success': sum(row['Y_business_ITT'] for row in rows),
            'pipeline_complete': sum(row['Z_pipeline_complete'] for row in rows),
            'coder_attempt_counts': {str(i): sum(row['coder_attempts'] == i for row in rows) for i in range(4)},
            'coder_attempts_unknown': sum(row['coder_attempts'] is None for row in rows),
            'experience': {state: sum(row['experience_status'] == state for row in rows) for state in EXPERIENCE},
            'resources': totals([row['resources'] for row in rows]),
        }
    return {'schema': 'persistent-memory.conf-public-summary.v1', 'registered_reduction': result,
            'secondary': secondary, 'shared_A_resources': totals(shared)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path, nargs='?', default=Path(__file__).resolve().parent)
    parser.add_argument('--calculate', action='store_true', help='emit results for an unsealed public projection')
    args = parser.parse_args()
    code = Path(__file__).resolve().parent
    for name, expected in MODULE_PINS.items():
        require(sha((code / name).read_bytes()) == expected, 'published module pin: ' + name)
    sys.path.insert(0, str(code))
    from reduce_conf_grades import reduce_conf_grades

    if not args.calculate:
        manifest = load(args.bundle / 'MANIFEST.json')
        exact(manifest, ('schema', 'files'), 'manifest')
        require(manifest['schema'] == 'persistent-memory.conf-public-manifest.v1', 'manifest schema')
        exact(manifest['files'], ('ROSTER.json', 'ARMS.json', 'RESULT.json', 'verify.py', *MODULE_PINS), 'manifest inventory')
        for name, expected in manifest['files'].items():
            path = code / name if name == 'verify.py' or name in MODULE_PINS else args.bundle / name
            require(isinstance(expected, str) and re.fullmatch(r'[0-9a-f]{64}', expected)
                    and sha(path.read_bytes()) == expected, 'manifest hash: ' + name)
    result = projection(args.bundle, reduce_conf_grades)
    if args.calculate:
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    else:
        require(canonical(result) == canonical(load(args.bundle / 'RESULT.json')), 'summary differs')
        print('Verified 32 worlds, 128 arm rows and the published summary.')


if __name__ == '__main__':
    main()
