def assess_experience_partitions(actual_lab, new_output_dir, *, qualified_support_path=None,
                                 qualified_support_sha256=None, expected_source_pins=None):
    """Closed XP evidence only: existing Registry, records and fresh CLI verifier."""
    import base64
    import collections
    import hashlib
    import importlib.util
    import json
    import os
    from pathlib import Path, PurePosixPath
    import subprocess
    import sys
    import time
    import types
    from datetime import datetime, timezone
    from hermes_policy_registry import Registry, identity, load_learning_records
    from hermes_policy_registry import registry as registry_module

    def check(condition, reason):
        if not condition:
            raise ValueError('experience_registry:' + reason)

    def read(path, maximum=64 * 1024 ** 2):
        path = Path(path)
        check(path.is_file() and not path.is_symlink() and path.stat().st_size <= maximum, 'bounded_file:' + path.name)
        return path.read_bytes()

    sha = lambda body: hashlib.sha256(body).hexdigest()
    canonical = registry_module.canonical
    lab, output = Path(actual_lab).resolve(strict=True), Path(new_output_dir)
    repo, python = lab / 'repo', lab / 'venv/bin/python'
    check(sys.platform == 'linux' and Path(sys.prefix).resolve() == (lab / 'venv').resolve(), 'actual_linux_venv')
    check(type(expected_source_pins) is dict and len(expected_source_pins) == 4, 'four_source_pins')
    pins = dict(expected_source_pins)
    fixed = {'benchmarks/action_transfer.py', 'benchmarks/run_benchmark.py'}
    check(fixed <= set(pins), 'fixed_consumer_sources')
    others = set(pins) - fixed
    fixture_names = [n for n in others if n.endswith('/SEALED-FIXTURE.json')]
    plan_names = [n for n in others if n.endswith('/PLAN.json')]
    check(len(fixture_names) == len(plan_names) == 1
          and PurePosixPath(fixture_names[0]).parent == PurePosixPath(plan_names[0]).parent, 'fixture_plan_names')
    for name, pin in pins.items():
        rel = PurePosixPath(name)
        check(not rel.is_absolute() and '..' not in rel.parts and '\\' not in name
              and rel.as_posix() == name and name.startswith('benchmarks/'), 'safe_source_path')
        check(type(pin) is str and len(pin) == 64 and all(c in '0123456789abcdef' for c in pin)
              and sha(read(repo / name)) == pin, 'source_pin:' + name)
    support_path = repo / 'benchmarks/action_transfer.py'
    check(Path(qualified_support_path).resolve() == support_path.resolve()
          and qualified_support_sha256 == pins['benchmarks/action_transfer.py'], 'exact_actual_support_required')
    spec = importlib.util.spec_from_file_location('_closed_experience_support_' + qualified_support_sha256[:16], support_path)
    support = importlib.util.module_from_spec(spec)
    check(spec.name not in sys.modules, 'support_import_conflict')
    sys.modules[spec.name] = support
    spec.loader.exec_module(support)
    decode = support.json_value
    candidate_raw, closure_raw, observations_raw = [read(lab / name) for name in ('candidate.json', 'RESULT.json', 'comparison.json')]
    candidate, closure, observations = map(decode, (candidate_raw, closure_raw, observations_raw))
    check(closure['candidate_sha256'] == sha(candidate_raw) and closure['source_drift'] is False
          and closure['production_changed'] is False and closure['purpose'] == 'experience_transfer'
          and closure['planned_rows'] == closure['terminal_rows'] == 288, 'closed_full_actual_xp_study')
    check(sha(observations_raw) == closure['comparison_sha256']
          and observations['schema'] == 'persistent-memory.experience-observations.v1'
          and observations['mode'] == 'paid' and observations['fake_proof_only'] is False
          and len(observations['rows']) == 288, 'paid_closed_xp_observations')
    for name, pin in pins.items():
        check(candidate['files'][name]['sha256'] == pin, 'candidate_source_binding')
    dataset, plan_pin = pins[fixture_names[0]], pins[plan_names[0]]
    fixture, plan = decode(read(repo / fixture_names[0])), decode(read(repo / plan_names[0]))
    check(fixture['schema'] == 'persistent-memory.experience-fixture.v1' and fixture['synthetic'] is True
          and plan['schema'] == 'persistent-memory.experience-plan.v1'
          and plan['dataset_sha256'] == observations['dataset_sha256'] == dataset
          and observations['plan_sha256'] == plan_pin, 'fixture_plan_observation_binding')
    helper = candidate['frozen_native_inputs']['fixture_contract.py']
    helper_raw = base64.b64decode(helper['base64'], validate=True)
    check(sha(helper_raw) == helper['sha256'] and len(helper_raw) == helper['bytes'], 'actual_frozen_contract')
    contract = types.ModuleType('_closed_experience_contract')
    exec(compile(helper_raw, 'fixture_contract.py', 'exec'), contract.__dict__)
    records = load_learning_records()
    check(sha(read(registry_module.__file__)) == support.REGISTRY_SHA256
          and sha(read(records.__file__)) == registry_module.RECORDS_SHA, 'registry_records_pins')
    core, typed = support._memory_modules()
    worlds = {w['world_id']: w for w in fixture['worlds']}
    cells = {c['cell_id']: c for c in plan['cells']}
    rows = {r['cell']['cell_id']: r for r in observations['rows']}
    episodes = {e['episode_id']: e for e in plan['episodes']}
    check(len(worlds) == 12 and len(cells) == len(plan['cells']) == 288 and len(rows) == 288
          and set(rows) == set(cells) and len(episodes) == len(plan['episodes']) == 48, 'finite_denominators')
    check(len({(w['family'], w['language']) for w in worlds.values()}) == 12, 'six_families_two_languages')
    membership, b_ids, episode_for = {}, [], {}
    for eid, episode in episodes.items():
        check(set(episode['b_cell_ids']) == {'derived', 'raw', 'none', 'withdrawn'}, 'four_real_xp_arms')
        mappings = [('A', episode['a_cell_id']), ('extract', episode['extract_cell_id']), *episode['b_cell_ids'].items()]
        for kind, cid in mappings:
            check(cid in cells and cid not in membership, 'unique_episode_cell')
            cell = cells[cid]
            check(cell['world_id'] == episode['world_id'] and cell['world_id'] in worlds
                  and cell['template_id'] == worlds[cell['world_id']]['template_id']
                  and cell['arm'] == ('none' if kind in ('A', 'extract') else kind), 'episode_cell_identity')
            world = contract.project_case(worlds[cell['world_id']], 'A' if kind in ('A', 'extract') else 'B')
            support.project_experience(world, cell, 'extract' if kind == 'extract' else 'propose',
                                       dataset_sha256=dataset, plan_sha256=plan_pin)
            membership[cid] = kind
            if kind not in ('A', 'extract'):
                b_ids.append(cid); episode_for[cid] = eid
        episode_cells = [cells[cid] for _, cid in mappings]
        check(len({(c['model'], c['repetition']) for c in episode_cells}) == 1, 'episode_model_repetition')
    check(set(membership) == set(cells) and len(b_ids) == 192
          and {(cells[e['a_cell_id']]['world_id'], cells[e['a_cell_id']]['model'], cells[e['a_cell_id']]['repetition'])
               for e in episodes.values()} == {(wid, model, rep) for wid in worlds for model in support.MODELS for rep in (1, 2)},
          'full_episode_grid')
    for cid, row in rows.items():
        check(row['cell'] == cells[cid] and row['dataset_sha256'] == dataset and row['plan_sha256'] == plan_pin,
              'row_cell_binding')
    check(not output.exists() and not output.is_symlink() and output.parent.is_dir()
          and not output.resolve().is_relative_to(lab) and not lab.is_relative_to(output.resolve()), 'separate_new_output')
    output.mkdir(mode=0o700)

    def write(path, value):
        raw = (canonical(value) + '\n').encode('utf-8')
        with path.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        path.chmod(0o600)
        return {'sha256': sha(raw), 'bytes': len(raw)}

    critical = {repo / n: pin for n, pin in pins.items()}
    critical.update({lab / 'candidate.json': sha(candidate_raw), lab / 'RESULT.json': sha(closure_raw),
                     lab / 'comparison.json': sha(observations_raw), Path(core.__file__): support.CORE_SHA256,
                     Path(typed.__file__): support.TYPED_SHA256, Path(registry_module.__file__): support.REGISTRY_SHA256,
                     Path(records.__file__): registry_module.RECORDS_SHA})
    contexts, groups = {}, collections.defaultdict(list)
    for cid in b_ids:
        cell, row = cells[cid], rows[cid]
        groups[(cell['model'], cell['arm'], cell['repetition'])].append(cid)
        if row['consume'] is None or row['verification'] is None:
            check(row['consume'] is None and row['verification'] is None, 'partial_B_receipts')
            continue  # Planned unknown retained below; no synthetic execution evidence.
        run = lab / 'cells' / cid / 'run'
        paths = {phase + '_' + name: run / phase / filename for phase in ('observe', 'propose', 'verify')
                 for name, filename in (('input', 'input.json'), ('receipt', 'receipt.json'), ('exit', 'EXIT.json'))}
        values = {key: decode(read(path)) for key, path in paths.items()}
        p1, p2, p3 = [values[p + '_receipt'] for p in ('observe', 'propose', 'verify')]
        check(p2 == row['consume'] and p3 == row['verification'] and p2['fake_proof_only'] is False
              and p3['fake_proof_only'] is False and sha(p2['prompt'].encode()) == p2['prompt_sha256'], 'actual_B_receipts')
        for phase, receipt in (('observe', p1), ('propose', p2), ('verify', p3)):
            exited = values[phase + '_exit']
            check(receipt['cell'] == cell and receipt['dataset_sha256'] == dataset and receipt['plan_sha256'] == plan_pin
                  and receipt['phase'] == phase and exited['pid'] == receipt['pid']
                  and exited['returncode'] == 0 and receipt['ended_ns'] <= exited['exited_ns'], 'actual_phase_exit')
        check(len({p1['pid'], p2['pid'], p3['pid']}) == 3
              and values['observe_exit']['exited_ns'] <= p2['started_ns']
              and values['propose_exit'] == p3['p2_exit']
              and values['propose_exit']['exited_ns'] <= p3['started_ns'], 'A_B_actual_process_order')
        case = worlds[cell['world_id']]
        world = contract.project_case(case, 'B')
        for phase in ('observe', 'propose', 'verify'):
            projected = dict(world, oracle=contract.get_oracle(case, 'B')) if phase == 'verify' else world
            check(values[phase + '_input'] == support.project_experience(projected, cell, phase,
                  dataset_sha256=dataset, plan_sha256=plan_pin), 'frozen_B_projection')
        for phase, prior, exited in (('propose', p1, values['observe_exit']), ('verify', p2, values['propose_exit'])):
            for label, value in (('prior-receipt', prior), ('prior-exit', exited)):
                path = run / phase / (label + '.json')
                check(decode(read(path)) == value, 'prior_receipt_exit_binding')
                paths[phase + '_' + label] = path
        episode = episodes[episode_for[cid]]
        extraction = rows[episode['extract_cell_id']]['consume']
        check(type(extraction) is dict and extraction['candidate_promoted'] is False, 'authentic_unpromoted_extraction')
        xpath = lab / 'cells' / episode['extract_cell_id'] / 'run/extract'
        check(decode(read(xpath / 'receipt.json')) == extraction, 'extraction_receipt_binding')
        xexit = decode(read(xpath / 'EXIT.json'))
        arow = rows[episode['a_cell_id']]
        adir = lab / 'cells' / episode['a_cell_id'] / 'run'
        a_bytes = {path.name: read(path, 16384) for path in (adir / 'artifacts').iterdir()}
        actual_feedback = contract.feedback_from_a(case, a_bytes, extraction['input']['feedback']['check_id'])
        check(actual_feedback == extraction['input']['feedback'], 'fresh_actual_A_business_feedback')
        check(extraction['cell'] == cells[episode['extract_cell_id']]
              and extraction['dataset_sha256'] == dataset and extraction['plan_sha256'] == plan_pin
              and xexit['pid'] == extraction['pid'] and xexit['returncode'] == 0
              and extraction['ended_ns'] <= xexit['exited_ns'] <= p1['started_ns'], 'extraction_before_fresh_B')
        check(extraction['input'] == support.experience_input(arow['consume'], arow['verification'], extraction['input']['feedback'])
              and extraction['a_exit'] == decode(read(adir / 'verify/EXIT.json'))
              and decode(read(xpath / 'prior-receipt.json')) == arow['consume']
              and decode(read(xpath / 'verification.json')) == arow['verification']
              and decode(read(xpath / 'prior-exit.json')) == extraction['a_exit'], 'actual_A_to_extraction_binding')
        for key, path in [('A_consume', adir / 'propose/receipt.json'), ('A_verification', adir / 'verify/receipt.json'),
                          ('A_exit', adir / 'verify/EXIT.json'), ('extraction_A', xpath / 'prior-receipt.json'),
                          ('extraction_P3', xpath / 'verification.json'), ('extraction_A_exit', xpath / 'prior-exit.json'),
                          ('extraction_feedback', xpath / 'feedback.json')]:
            paths[key] = path
        check(decode(read(paths['A_consume'])) == arow['consume']
              and decode(read(paths['A_verification'])) == arow['verification']
              and decode(read(paths['extraction_feedback'])) == extraction['input']['feedback'], 'actual_A_file_binding')
        if cell['arm'] != 'none':
            for label, value in (('extraction', extraction), ('extraction-exit', decode(read(xpath / 'EXIT.json')))):
                path = run / 'observe' / (label + '.json')
                check(decode(read(path)) == value, 'fresh_B_prior_extraction')
                paths['observe_' + label] = path
            check(p1['extraction_exit'] == decode(read(xpath / 'EXIT.json')), 'extraction_exit_in_P1')
        paths['actual_extraction'] = xpath / 'receipt.json'; paths['actual_extraction_exit'] = xpath / 'EXIT.json'
        contexts[cid] = {'cell': cell, 'row': row, 'run': run, 'values': values, 'p1': p1, 'p2': p2, 'p3': p3,
                         'paths': paths, 'pins': {key: sha(read(path)) for key, path in paths.items()},
                         'extraction': extraction, 'world': world}
    check(len(groups) == 16 and all(len(ids) == 12 for ids in groups.values()), 'sixteen_twelve_world_partitions')
    environment = {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'PIP_NO_INDEX': '1'}
    summaries, labels, causes, callback_total = [], {}, {}, 0
    original_labels = {cid: rows[cid]['verification']['task_success'] if cid in contexts
                       and rows[cid]['consume']['status'] == 'completed'
                       and rows[cid]['verification']['effect_verified'] is True else None for cid in b_ids}
    created = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    for index, (partition, planned) in enumerate(sorted(groups.items()), 1):
        model, arm, repetition = partition
        ids = [cid for cid in sorted(planned) if cid in contexts]
        folder = output / ('partition-' + format(index, '02d')); folder.mkdir(mode=0o700)
        for cid in planned:
            labels[cid] = None
            causes[cid] = {'classification': 'unknown', 'reason': 'B_unavailable_or_unverified', 'recurrence': None}
        if not ids:
            summaries.append({'model': model, 'arm': arm, 'repetition': repetition, 'planned_worlds': 12,
                              'registry_runs': 0, 'assessment': None, 'unknown': 12, 'runtime_activated': False})
            continue
        witnesses = {}
        def remember(value, record=False):
            reference = records.record_id(value) if record else identity(value)
            if record: records.validate(value)
            check(reference not in witnesses or witnesses[reference] == (value, record), 'witness_conflict')
            witnesses[reference] = (value, record); return reference
        implementation = 'sha256:' + pins['benchmarks/action_transfer.py']
        policy = {'schema': 'experience-executed-policy-v1', 'model': model, 'arm': arm, 'repetition': repetition,
                  'support_sha256': pins['benchmarks/action_transfer.py'], 'plan_sha256': plan_pin,
                  'budget': {'top_k': 5, 'max_context_chars': 8000}, 'candidate_promoted': False}
        policy_ref = remember(policy)
        configuration = remember({'schema': 'execution-policy-set-v1', 'policy_refs': [policy_ref]})
        rule = remember({'schema': 'experience-transfer-rule-v1', 'world_ids': sorted(worlds), 'plan_sha256': plan_pin,
            'experience_bindings': {cid: {'extraction_receipt_sha256': contexts[cid]['pins']['actual_extraction'],
                'memory_refs': contexts[cid]['p1'].get('experience'), 'candidate_promoted': False} for cid in ids},
            'lesson_is_not_business_authority': True})
        oracle = remember({'schema': 'experience-B-oracle-v1', 'fixture_sha256': dataset,
                           'contract_sha256': helper['sha256'], 'verification': 'frozen_P3_fresh_process'})
        safety = remember({'assessment_only': True, 'provider_requests': 0, 'production_changed': False})
        protocol = {'schema_version': 1, 'family': 'workflow', 'safety_contract_ref': safety,
                    'judge': {'kind': 'executable', 'identifier': 'native-workflow-effects-v1', 'revision': '1'},
                    'rubric_refs': [oracle], 'min_observed': 12, 'min_success_rate': 1.0,
                    'max_unobserved': 0, 'max_p95_ratio': 1000000000.0}
        remember(protocol)
        registry = Registry.create(folder / 'registry.sqlite', records, protocol)
        artifact = {'schema_version': 1, 'family': 'workflow', 'name': 'experience-B-' + str(index),
                    'implementation_ref': implementation, 'configuration_ref': configuration,
                    'safety_contract_ref': safety, 'execution_policy_refs': [policy_ref],
                    'dependencies': [rule, oracle, 'sha256:' + dataset, 'sha256:' + plan_pin,
                                     'sha256:' + pins['benchmarks/run_benchmark.py']]}
        remember(artifact); proposed = registry.propose(artifact)
        runs = [support.workflow_evidence(contexts[cid]['p2'], contexts[cid]['p3'], records=records,
                    policy=policy, implementation_ref=implementation, configuration_ref=configuration,
                    rule_ref=rule, oracle_ref=oracle, created_at=created) for cid in ids]
        report = {'schema': 'native-workflow-effects-v1', 'version': 1, 'dataset_sha256': dataset,
                  'rule_ref': rule, 'oracle_ref': oracle, 'runs': runs}
        remember(report); report_ref = registry.add_report(report)
        for run in runs:
            for value in [run['policy'], run['outcome'], *run['source_snapshots'],
                          run['outcome']['consumer_action_observation'], run['reopened_effect']]: remember(value)
            for value in run['records'].values(): remember(value, True)
        run_by_id = {run['run_id']: run for run in runs}
        callbacks, validations = [], []
        def revalidate(required):
            failures = []
            for path, pin in critical.items():
                if sha(read(path)) != pin: failures.append('source_or_closure_changed:' + path.name)
            for cid in ids:
                context = contexts[cid]
                for key, path in context['paths'].items():
                    if sha(read(path)) != context['pins'][key]: failures.append('phase_evidence_changed:' + cid)
                try:
                    state, memory, _ = support._open_state(context['run'] / 'state', context['values']['propose_input'],
                                                          context['p2']['p1_state_sha256'])
                    packet = context['p2']['packet']
                    if state['checkpoint'] != packet['checkpoint'] or not support._revalidate_packet(memory, packet):
                        failures.append('current_packet_invalid:' + cid)
                    task = context['world']['task']
                    for operation in context['p2']['writes']:
                        source = task['target_dependencies'][operation['target']]
                        if source is not None:
                            actual = support._dependency_status(memory, context['values']['propose_input']['workspace'], source, task)
                            if actual['status'] != 'current' or actual['ref'] != operation['authority_check'].get('ref'):
                                failures.append('business_authority_invalid:' + cid)
                    stored = state.get('experience')
                    if arm != 'none':
                        if stored != context['p1']['experience']: failures.append('stored_experience_binding:' + cid)
                        for field in ('raw_ref', 'procedure_ref'):
                            reference = stored[field]
                            if reference is None: continue
                            decision = memory.read(reference)
                            if arm == 'withdrawn':
                                if decision['allowed'] or decision.get('content') is not None: failures.append('withdrawal_body_exposed:' + cid)
                            elif not decision['allowed']:
                                failures.append('experience_not_current:' + cid)
                            else:
                                expected = context['extraction']['input' if field == 'raw_ref' else 'procedure']
                                if typed.decode(decision['content'])['text'] != canonical(expected): failures.append('experience_body_changed:' + cid)
                except Exception as error:
                    failures.append('memory_revalidation:' + cid + ':' + type(error).__name__)
            raw_witnesses = {'sha256:' + pin: path for path, pin in critical.items()}
            checked = []
            for ref in required:
                if ref in raw_witnesses: valid = 'sha256:' + sha(read(raw_witnesses[ref])) == ref
                elif ref in witnesses:
                    value, record = witnesses[ref]
                    valid = (records.record_id(value) if record else identity(value)) == ref
                else: valid = False
                if valid: checked.append(ref)
                else: failures.append('unknown_reference:' + ref)
            validations.append({'worlds_revalidated': len(ids), 'status': 'valid' if not failures else 'unverified', 'failures': failures})
            return {'status': 'valid' if not failures and set(checked) == set(required) else 'unverified', 'checked': checked}

        def callback(envelope):
            cid = envelope['run']['run_id']; context = contexts[cid]
            check(canonical(envelope['run']) == canonical(run_by_id[cid]) and envelope['rule_ref'] == rule
                  and envelope['oracle_ref'] == oracle and envelope['dataset_ref'] == 'sha256:' + dataset, 'callback_binding')
            fresh_path = folder / ('fresh-' + str(len(callbacks) + 1) + '.json')
            began = time.monotonic_ns()
            command = [str(python), '-I', '-B', str(repo / 'benchmarks/run_benchmark.py'), '--action-transfer', '--action-phase', 'verify']
            for option, key in (('input', 'verify_input'), ('prior-receipt', 'propose_receipt'), ('prior-exit', 'propose_exit')):
                command += ['--action-' + option, str(context['paths'][key]), '--action-' + option + '-sha256', context['pins'][key]]
            command += ['--action-artifacts', str(context['run'] / 'artifacts'), '--action-output', str(fresh_path)]
            process = subprocess.run(command, cwd=folder, env=environment, capture_output=True, timeout=60)
            check(process.returncode == 0 and fresh_path.is_file(), 'fresh_verifier_failed')
            raw = read(fresh_path); check(process.stdout == raw, 'fresh_stdout_binding')
            fresh = decode(raw)
            checked = support.workflow_verifier_result(envelope, fresh, reopened_after_ns=began)
            if checked['status'] == 'verified':
                labels[cid] = run_by_id[cid]['records']['evaluation']['success']
                case = worlds[cells[cid]['world_id']]
                variants = {name: contract.expected_business(case['family'], 'B', case['B']['task']['data'], name)
                            for name in contract.CONVENTIONS[case['family']]}
                targets = {target for target, body, fmt in variants.values()}; check(len(targets) == 1, 'public_variant_target')
                target = next(iter(targets)); path = context['run'] / 'artifacts' / target
                actual_body = read(path, 16384) if path.is_file() and not path.is_symlink() else None
                inventory = fresh['observed_inventory'].get(target)
                check(actual_body is None or (type(inventory) is dict and inventory.get('kind') == 'file'
                      and inventory.get('sha256') == sha(actual_body)), 'fresh_business_bytes')
                matches = [name for name, (_, body, fmt) in variants.items() if body == actual_body]
                wrong = matches[0] != case['receiver_convention'] if len(matches) == 1 else None
                a_feedback = context['extraction']['input']['feedback']
                prior_mismatch = a_feedback['observed']['discriminating'] and a_feedback['success'] is False
                causes[cid] = {'classification': 'receiver_mismatch' if wrong is True else 'receiver_match' if wrong is False else 'unknown_wrong_cause',
                               'artifact_sha256': sha(actual_body) if actual_body is not None else None,
                               'attempted_convention': matches[0] if len(matches) == 1 else None,
                               'A_receiver_mismatch': bool(prior_mismatch), 'recurrence': wrong if prior_mismatch else None}
            callbacks.append({'cell_id': cid, 'status': checked['status'], 'fresh_receipt_sha256': sha(raw),
                              'fresh_pid': fresh['pid'], 'task_success': fresh['task_success'], 'B_feedback': causes[cid]})
            return checked

        event = registry.evaluate_workflow_effect_reports(proposed['policy_ref'],
                [{'report_ref': report_ref, 'run_id': run['run_id']} for run in runs], None, proposed['seq'], revalidate, callback)
        inspected = registry.inspect(proposed['policy_ref']); assessment = inspected['assessment']
        check(len(validations) == 1 and validations[0]['status'] == 'valid'
              and validations[0]['worlds_revalidated'] == len(ids), 'fresh_current_dependencies_required')
        check(inspected['runtime_activated'] is False and assessment['runtime_activated'] is False
              and assessment['eligible_for_admission_review'] is False
              and 'native_full_cost_unavailable' in assessment['reasons'], 'no_admission_or_activation')
        for run in assessment['runs']:
            expected = labels[run['run_id']]
            check(run['success'] is expected and run['native_label_current'] is True
                  and (expected is None or run['native_effect_verified'] is True), 'preserved_original_label')
        for name, value in [('REPORT', report), ('EVENT', event), ('ASSESSMENT', assessment),
                            ('CALLBACKS', callbacks), ('REVALIDATION', validations)]: write(folder / (name + '.json'), value)
        callback_total += len(callbacks)
        summaries.append({'model': model, 'arm': arm, 'repetition': repetition, 'planned_worlds': 12,
                          'registry_runs': len(ids), 'assessment': assessment, 'callbacks': callbacks,
                          'revalidation': validations, 'unknown': sum(labels[cid] is None for cid in planned), 'runtime_activated': False})
    quality = {'denominator': 192, 'successes': sum(v is True for v in labels.values()),
               'failures': sum(v is False for v in labels.values()), 'unknown': sum(v is None for v in labels.values())}
    check(len(labels) == 192 and labels == original_labels
          and sum(quality[k] for k in ('successes', 'failures', 'unknown')) == 192, 'all_B_denominators_and_labels')
    summary = {'schema': 'hermes.experience-transfer.actual-registry-assessments.v1', 'original_cells': 288,
               'planned_B_cells': 192, 'partition_count': 16, 'worlds_per_partition': 12, 'partitions': summaries,
               'dataset_sha256': dataset, 'plan_sha256': plan_pin, 'comparison_sha256': sha(observations_raw),
               'aggregation_adapter_sha256': qualified_support_sha256, 'aggregation_adapter_changed_functions': [],
               'quality': quality, 'B_labels': labels, 'B_feedback': causes, 'fresh_callback_count': callback_total,
               'original_quality_labels_preserved': True,
               'provider_requests': 0, 'credential_reads': 0, 'runtime_activated': False, 'eligible_for_admission_review': False,
               'production_changed': False, 'cost_report_ref': None, 'helper_sha256': helper['sha256'],
               'unknown_scope': 'Unexecuted B has no invented Registry run; generic failure is never called receiver recurrence.'}
    write(output / 'SUMMARY.json', summary)
    return summary