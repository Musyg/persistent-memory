"""Regrade disclosed synthetic B responses with the original inert oracle."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
from verify import ARMS, WORLDS, exact, load, require, sha


ORACLE_PIN = '1226a8864371441d766833c65e0bec53839dc5653b70f71ecb6a0ff539a32c46'
FILES = ('B-EVIDENCE.json', 'ORACLE-SOURCES.json', 'typed_b_oracle.py', 'verify_regrading.py')
STAGES = ('first', 'terminal')
AVAILABILITY = ('EXACT', 'WITHHELD', 'UNAVAILABLE')
SAFE_ROW_ID = re.compile(r'[0-9a-f]{4}-[abc]')
RESTRICTED_TEXT = re.compile(
    r'https?://|/(?:home|opt|dev|mnt|run|etc|proc|var|tmp|srv|usr)/|(?<![A-Za-z0-9_])[A-Za-z]:[\\/]|'
    r'-----BEGIN |(?:sk-|ghp_|github_pat_)[A-Za-z0-9_\-]{12,}|\bBearer\s+[A-Za-z0-9._\-]{10,}', re.I,
)


def oracle():
    sources = load(HERE / 'ORACLE-SOURCES.json')
    require(sources['distribution_license'] == 'MIT'
            and sources['typed_b_oracle_sha256'] == ORACLE_PIN
            and sha((HERE / 'typed_b_oracle.py').read_bytes()) == ORACLE_PIN, 'inert oracle pin')
    import typed_b_oracle

    require(Path(typed_b_oracle.__file__).resolve() == HERE / 'typed_b_oracle.py', 'unexpected oracle path')
    return typed_b_oracle


def check_evidence(evidence, bundle):
    judge = oracle()
    roster = load(bundle / 'ROSTER.json')['worlds']
    results = load(bundle / 'ARMS.json')['rows']
    public_worlds = {row['world']: row['case_join_sha256'] for row in roster}
    arms = {(row['world'], row['arm']): row for row in results}
    require(set(public_worlds) == WORLDS and len(roster) == 32, 'public roster shape')
    require(set(arms) == {(world, arm) for world in WORLDS for arm in ARMS} and len(results) == 128,
            'public arm shape')
    exact(evidence, ('schema', 'fixtures', 'returns'), 'evidence')
    require(evidence['schema'] == 'persistent-memory.conf-regrading.v1', 'evidence schema')
    require(type(evidence['fixtures']) is list and len(evidence['fixtures']) == 32, 'fixture count')
    fixtures = {}
    for row in evidence['fixtures']:
        exact(row, ('world', 'case_join_sha256', 'threshold', 'convention_id', 'rows', 'oracle'), 'fixture')
        world = row['world']
        require(world in public_worlds and world not in fixtures
                and row['case_join_sha256'] == public_worlds[world], 'fixture identity')
        records = row['rows']
        require(type(row['threshold']) is int and row['convention_id'] in judge.RULES, 'threshold contract')
        require(type(records) is list and len(records) == 3, 'input rows')
        for record in records:
            exact(record, ('record_id', 'value'), 'record')
            require(type(record['record_id']) is str and SAFE_ROW_ID.fullmatch(record['record_id'])
                    and type(record['value']) is int, 'synthetic input row')
        require(len({record['record_id'] for record in records}) == len(records), 'duplicate synthetic row')
        eligible = judge.expected_eligible({'threshold': row['threshold'],
                                           'values': [record['value'] for record in records]}, row['convention_id'])
        expected = [[record['record_id'], str(record['value'])]
                    for record, keep in zip(records, eligible, strict=True) if keep]
        require(row['oracle'] == {'columns': ['record_id', 'value'], 'rows': expected}, 'oracle differs from B contract')
        fixtures[world] = row['oracle']

    require(type(evidence['returns']) is list and len(evidence['returns']) == 128, 'return row count')
    seen, counts = set(), Counter()
    for row in evidence['returns']:
        exact(row, ('world', 'arm', 'case_join_sha256', *STAGES), 'return row')
        world, arm = row['world'], row['arm']
        key = (world, arm)
        require(key in arms and key not in seen and row['case_join_sha256'] == public_worlds[world]
                == arms[key]['case_join_sha256'], 'return identity')
        seen.add(key)
        verdict = arms[key]
        attempts = verdict['coder_attempts']
        for stage in STAGES:
            answer = row[stage]
            state = answer['availability']
            require(state in AVAILABILITY, 'return availability')
            counts[stage, state] += 1
            if state != 'EXACT':
                exact(answer, ('availability',), 'undisclosed return')
                continue
            exact(answer, ('availability', 'content', 'sha256'), 'exact return')
            content = answer['content']
            require(type(content) is str and len(content.encode()) <= 32768
                    and sha(content.encode()) == answer['sha256'], 'return content hash or size')
            require(not RESTRICTED_TEXT.search(content), 'restricted material in response')
            require(type(attempts) is int and 1 <= attempts <= 3, 'attempt identity unknown')
            record = judge.coder_record(content, 1 if stage == 'first' else attempts)
            require(not any(RESTRICTED_TEXT.search(value) for value in (record['code'], record['filename'])
                            if isinstance(value, str)), 'restricted material in decoded artifact')
            grade = (judge.invalid_response() if record['code'] is None
                     else judge.artifact_verdict(fixtures[world], record, judge.business_b_oracle))
            field = 'first_attempt_business_passed' if stage == 'first' else 'business_passed'
            require(type(verdict[field]) is bool and grade['business_passed'] is verdict[field],
                    'independent B grade differs from published grade')
        if attempts == 1 and all(row[stage]['availability'] == 'EXACT' for stage in STAGES):
            require(row['first']['sha256'] == row['terminal']['sha256'], 'one attempt has two responses')
    return {stage: {state: counts[stage, state] for state in AVAILABILITY} for stage in STAGES}


def manifest(bundle, evidence_raw):
    files = {name: sha((HERE / name).read_bytes()) for name in FILES if name != 'B-EVIDENCE.json'}
    files['B-EVIDENCE.json'] = sha(evidence_raw)
    return {'schema': 'persistent-memory.conf-regrading-manifest.v1', 'files': files,
            'public_inputs': {name: sha((bundle / name).read_bytes()) for name in ('ROSTER.json', 'ARMS.json')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path, nargs='?', default=HERE.parent)
    args = parser.parse_args()
    evidence = HERE / 'B-EVIDENCE.json'
    require(manifest(args.bundle, evidence.read_bytes()) == load(HERE / 'REGRADING-MANIFEST.json'), 'regrading manifest')
    print(json.dumps(check_evidence(load(evidence), args.bundle), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
