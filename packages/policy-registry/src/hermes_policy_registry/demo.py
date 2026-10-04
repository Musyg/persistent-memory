"""Offline synthetic evidence transitions; no retrieval, judge or service calls."""
import argparse
import json
from importlib.resources import files
from pathlib import Path

from .registry import Registry, identity, load_learning_records


def run(directory):
    fixture = json.loads(files('hermes_policy_registry').joinpath('fixtures/demo.json').read_text())
    if fixture['data_class'] != 'synthetic_demo_not_measurement':
        raise ValueError('synthetic_fixture_required')
    directory = Path(directory)
    directory.mkdir(mode=0o700, exist_ok=False)
    directory.chmod(0o700)
    records = load_learning_records()
    code = fixture['implementation_sha256']
    case = fixture['case_id']
    dataset = identity(fixture).removeprefix('sha256:')
    execution = {'id': 'synthetic-demo', 'implementation_sha256': code,
                 'budget': {'top_k': 1, 'max_context_chars': 100}}
    safety = identity({'authorization_changes': False, 'synthetic': True})
    rubric = identity({'rubric': 'invented-demo-label', 'synthetic': True})
    judge = {'kind': 'executable', 'identifier': 'synthetic-demo-fixture', 'revision': '1'}
    protocol = {'schema_version': 1, 'family': 'retrieval', 'safety_contract_ref': safety,
                'judge': judge, 'rubric_refs': [rubric], 'min_observed': 1,
                'min_success_rate': 1.0, 'max_unobserved': 0,
                'max_p95_ratio': fixture['max_p95_ratio']}
    registry = Registry.create(directory / 'registry.sqlite', records, protocol)
    refs = {'synthetic-doc': fixture['source']}
    outcome = {'execution_status': 'completed', 'synthetic': True}
    experience = records.seal({'schema_version': records.VERSION, 'kind': 'experience',
                              'created_at': '2026-10-04T00:00:00Z', 'case_id': case,
                              'family': 'retrieval', 'policy_ref': identity(execution),
                              'source_refs': [identity({'doc_id': key, 'ref': value}) for key, value in sorted(refs.items())],
                              'lineage_status': 'observed', 'outcome_ref': identity(outcome)})
    evaluation = records.seal({'schema_version': records.VERSION, 'kind': 'evaluation',
                              'created_at': '2026-10-04T00:00:01Z', 'experience_ref': experience['record_id'],
                              'status': 'observed', 'success': fixture['quality']['success'],
                              'score': fixture['quality']['score'], 'judge': judge,
                              'rubric_ref': rubric, 'reason': None, 'supersedes': None})
    quality = {'dataset_sha256': dataset, 'runs': [
        {'run_id': 'demo-run', 'task_id': case, 'policy': execution, 'refs': refs,
         'outcome': outcome, 'records': {'experience': experience, 'evaluation': evaluation}}]}
    durations = {'core_lexical_budgeted': fixture['baseline_wall_ns'],
                 'typed_r3': fixture['candidate_wall_ns']}
    cost = {'kind': 'r4_serial_development_cost_screen_not_promotion',
            'dataset_sha256': dataset, 'r3_sha256': code, 'r4_sha256': 'b' * 64,
            'unchanged_ratio_limit': fixture['max_p95_ratio'],
            'summary': {key: {'wall': {'p95_ms': value / 1e6, 'count': 1}} for key, value in durations.items()},
            'samples': [{'policy': key, 'task_id': case, 'repeat': 0,
                         'execution_status': 'completed', 'wall_ns': value} for key, value in durations.items()],
            'functional_parity_and_no_mutation': True, 'failures': []}
    quality_ref, cost_ref = registry.add_report(quality), registry.add_report(cost)
    executed = [identity(execution)]
    artifact = {'schema_version': 1, 'family': 'retrieval', 'name': 'synthetic-demo-policy',
                'implementation_ref': 'sha256:' + code,
                'configuration_ref': identity({'schema': 'execution-policy-set-v1', 'policy_refs': executed}),
                'safety_contract_ref': safety, 'execution_policy_refs': executed, 'dependencies': []}
    proposed = registry.propose(artifact)
    ref = proposed['policy_ref']
    assessed = registry.evaluate_retrieval_reports(ref, [{'report_ref': quality_ref, 'run_id': 'demo-run'}],
                                                  cost_ref, 'typed_r3', proposed['seq'])
    # This explicitly trusted fixture callback is not a production authority adapter.
    admitted = registry.admit(ref, assessed['seq'], lambda values: {'status': 'valid', 'checked': list(values)})
    reopened = Registry(directory / 'registry.sqlite', records)
    before = reopened.inspect(ref)
    if before['effective_state'] != 'admitted' or before['runtime_activated']:
        raise RuntimeError('unexpected_demo_admission')
    reopened.revoke(experience['source_refs'][0], 'synthetic source withdrawal')
    after = reopened.inspect(ref)
    if after['effective_state'] != 'rollback' or not after['dependency_revoked']:
        raise RuntimeError('withdrawal_not_effective')
    result = {'data_class': fixture['data_class'], 'policy_ref': ref,
              'record_refs': [experience['record_id'], evaluation['record_id']],
              'state_before_withdrawal': before['effective_state'],
              'state_after_withdrawal': after['effective_state'],
              'runtime_activated': after['runtime_activated'],
              'measured_performance': False, 'retrieval_calls': 0, 'provider_calls': 0,
              'validator': 'trusted_synthetic_fixture_only'}
    (directory / 'demo.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, help='New directory; existing paths are refused')
    args = parser.parse_args(argv)
    print(json.dumps(run(args.directory), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
