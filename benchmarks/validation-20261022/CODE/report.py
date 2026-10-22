"""Linux reporting over bound normalized receipts; no provider or new scorer."""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ANALYSIS_SHA = 'edb74bc815cb35e56e68b7b78d2af9b76eb396b08a9e62d787e18df9ec87c7f6'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encode = lambda value: (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read_ref(root, ref):
    require(set(ref) == {'path', 'sha256'}, 'reference_shape')
    rel = Path(ref['path'])
    path = root / rel
    require(not rel.is_absolute() and '..' not in rel.parts and path.is_file() and not path.is_symlink()
            and path.resolve().is_relative_to(root.resolve()), 'reference_path')
    raw = path.read_bytes()
    require(len(raw) <= 64 * 1024 ** 2 and sha(raw) == ref['sha256'], 'reference_pin')
    return raw


def flatten(plan):
    require(plan['schema'] == 'persistent-memory.volume.phase-plan.v1' and plan['purpose'] == 'generation', 'plan_scope')
    return [{'cell_id': c['cell_id'], 'case_id': c['task_id'], 'model': b['budget']['model'],
             'repetition': int(c['stage'][-1]), 'arm': c['arm']}
            for b in plan['blocks'] for c in b['budget']['cells']]


def comparison(a, metadata, episodes, model, arm_a, arm_b, seed):
    scores = {m['case_id']: {'memory_on': [None] * 3, 'memory_off': [None] * 3} for m in metadata}
    for row in episodes:
        if row['model'] == model and row['case_id'] in scores and row['arm'] in (arm_a, arm_b):
            key = 'memory_on' if row['arm'] == arm_a else 'memory_off'
            scores[row['case_id']][key][row['repetition'] - 1] = row['success']
    stats = a.primary_interval(metadata, scores, samples=10000, seed=seed)
    first = Counter(a.outcome(s['memory_on'][0], s['memory_off'][0]) for s in scores.values())
    return {'model': model, 'arm_a': arm_a, 'arm_b': arm_b, 'secondary': True,
            'statistics': stats, 'first_repetition_pairs': dict(first)}


def emission_counts(rows):
    counts = Counter({'confirmed_emitted': 0, 'unknown_emission': 0, 'confirmed_not_emitted': 0, 'not_executed': 0})
    for row in rows:
        called = row.get('provider_called')
        require(type(called) in (bool, type(None)), 'emission_type')
        unknown = row.get('emission_unknown') is True or called is None
        require(not (row.get('emission_unknown') is True and called is not None), 'contradictory_emission_state')
        counts['unknown_emission' if unknown else 'confirmed_emitted' if called is True else 'confirmed_not_emitted'] += 1
        counts['not_executed'] += row.get('status') == 'not_executed'
    return dict(counts)


def build_report(manifest_path, pin):
    require(sys.platform == 'linux', 'linux_runtime_required')
    raw = manifest_path.read_bytes()
    require(sha(raw) == pin, 'report_manifest_not_frozen')
    config = json.loads(raw)
    require(config['schema'] == 'persistent-memory.volume.reporting-inputs.v1'
            and type(config['development_only']) is bool, 'report_scope')
    root = manifest_path.resolve().parent
    required = {'analysis', 'study_freeze', 'metadata', 'generation_plan', 'subset', 'generations', 'judgments'}
    require(required <= set(config['inputs']) <= required | {'accounting'}, 'report_inputs')
    bodies = {key: read_ref(root, ref) for key, ref in config['inputs'].items()}
    require(sha(bodies['analysis']) == ANALYSIS_SHA, 'different_analysis_source')
    spec = importlib.util.spec_from_file_location('frozen_volume_analysis', root / config['inputs']['analysis']['path'])
    a = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(a)
    values = {key: json.loads(body) for key, body in bodies.items() if key != 'analysis'}
    freeze = values['study_freeze']
    require(freeze['schema'] == 'persistent-memory.volume.study-freeze.v1'
            and freeze['holdout_outputs_observed'] == 0, 'study_freeze_scope')
    design = freeze.get('study_design')
    if design is None:
        # Preserve the closed V21 contract; smaller cohorts require an explicit
        # prospective design, not merely edited denominator fields.
        require(freeze['cases'] == 500 and freeze['latent_groups'] == 100
                and freeze['planned_episodes'] == 3900, 'study_freeze_scope')
    else:
        require(type(design) is dict and freeze['cases'] == design['planned_tasks']
                and freeze['latent_groups'] == design['scenario_groups']
                and freeze['planned_episodes'] == design['planned_episodes'], 'study_design_freeze_binding')
    tasks, groups, episode_count = freeze['cases'], freeze['latent_groups'], freeze['planned_episodes']
    require(type(tasks) is int and 1 <= tasks <= 500 and type(groups) is int and 1 <= groups <= tasks
            and type(episode_count) is int and 1 <= episode_count <= 3900, 'bounded_study_denominators')
    secondary = freeze['secondary_analysis']
    require(secondary['Luna_A_minus_C_subset100_seed'] == 20261025
            and secondary['Sol_A_minus_B_subset100_seed'] == 20261026, 'secondary_seeds_not_frozen')
    for field, name in (('metadata', 'METADATA.json'), ('subset', 'SUBSET.json'), ('analysis', 'volume_analysis.py')):
        require(sha(bodies[field]) == freeze['frozen_members'][name]['sha256'], 'study_member_binding')
    metadata = values['metadata']['cases']
    plan = flatten(values['generation_plan'])
    subset = values['subset']['case_ids']
    require(len(subset) == len(set(subset)) == 100, 'secondary_subset')
    require(len(metadata) == len({row['case_id'] for row in metadata}) == tasks
            and len({row['scenario_group'] for row in metadata}) == groups
            and len(plan) == len({row['cell_id'] for row in plan}) == episode_count
            and {row['case_id'] for row in plan} == {row['case_id'] for row in metadata}, 'declared_actual_denominators')
    require(design is None or design['secondary_case_ids'] == subset, 'study_design_subset_binding')
    generations, judgments = values['generations'], values['judgments']
    require(generations['schema'] == 'persistent-memory.volume.normalized-generations.v1'
            and generations['development_only'] is config['development_only']
            and generations['oracle_opened'] is False and generations['planned_episodes'] == episode_count
            and generations['generation_plan_sha256'] == sha(bodies['generation_plan'])
            and generations['cases_sha256'] == freeze['frozen_members']['CASES.json']['sha256'], 'generation_binding')
    require(judgments['schema'] == 'persistent-memory.volume.normalized-judgments.v1'
            and judgments['generations_sha256'] == sha(bodies['generations'])
            and judgments['planned_generation_episodes'] == episode_count, 'judgments_binding')
    require({p['case_id'] for p in plan if p['arm'] == 'simple_baseline'} == set(subset), 'subset_plan_binding')
    planned = {p['cell_id']: p for p in plan}
    require(set(generations['results']) == set(planned), 'normalized_full_planned_denominator')
    policies = {'memory_on': 'typed_fts_budgeted', 'memory_off': 'no_memory', 'simple_baseline': 'core_lexical_budgeted'}
    for key, row in generations['results'].items():
        if row.get('status') == 'not_executed':
            item = planned[key]
            require(row['cell_id'] == key and row['case_id'] == item['case_id']
                    and row['repetition'] == item['repetition'] - 1 and row['policy_id'] == policies[item['arm']]
                    and row.get('provider_called') is False and row.get('body') is None, 'placeholder_binding')
    # The frozen aggregate represents unexecuted episodes by an absent result.
    # Normalized receipts deliberately retain explicit placeholders for visibility.
    results = {key: row for key, row in generations['results'].items() if row.get('status') != 'not_executed'}
    report = a.aggregate_campaign(metadata, plan, results, judgments['judgments'], samples=10000, study_design=design)
    episodes = report['episodes']
    selected = [m for m in metadata if m['case_id'] in subset]
    secondaries = [comparison(a, selected, episodes, 'gpt-6-luna', 'memory_on', 'simple_baseline', 20261025),
                   comparison(a, selected, episodes, 'gpt-6.1-sol', 'memory_on', 'memory_off', 20261026)]
    pass3, latencies = defaultdict(dict), []
    scores = defaultdict(lambda: [None] * 3)
    by_pair = defaultdict(dict)
    by_family = defaultdict(list)
    for row in episodes:
        scores[(row['model'], row['arm'], row['case_id'])][row['repetition'] - 1] = row['success']
        if row['model'] == 'gpt-6-luna' and row['arm'] in ('memory_on', 'memory_off') and row['repetition'] == 1:
            by_pair[row['case_id']][row['arm']] = row['success']
    for (model, arm, _), triple in scores.items():
        verdict = a.pass_three(triple)
        label = 'unknown' if verdict is None else 'success' if verdict else 'failure'
        key = model + '/' + arm
        pass3[key][label] = pass3[key].get(label, 0) + 1
    for task in report['primary']['tasks']:
        by_family[task['family']].append(task)
    family_rows = []
    for family, tasks in sorted(by_family.items()):
        pairs = Counter(a.outcome(by_pair[t['case_id']].get('memory_on'), by_pair[t['case_id']].get('memory_off')) for t in tasks)
        family_rows.append({'family': family, 'planned_tasks': len(tasks), 'exploratory': True,
             'point_effect_bounds': [sum(t[k] for t in tasks) / len(tasks) for k in ('effect_lower', 'effect_upper')],
             'first_repetition_pairs': dict(pairs)})
    for group in report['by_model_arm']:
        cells = [p['cell_id'] for p in plan if p['model'] == group['model'] and p['arm'] == group['arm']]
        emitted = emission_counts(generations['results'][cell_id] for cell_id in cells)
        group.pop('emitted')
        group['emission_status'] = emitted
        case_ids = {planned[cell_id]['case_id'] for cell_id in cells}
        delivery_scores = {cid: {'memory_on': [False] * 3, 'memory_off': [False] * 3} for cid in case_ids}
        for cell_id in cells:
            row = results.get(cell_id, {})
            delivered = (row.get('status') == 'completed' and row.get('provider_called') is True
                         and row.get('response_model') == group['model'] and isinstance(row.get('body'), str)
                         and bool(row['body'].strip()))
            item = planned[cell_id]
            delivery_scores[item['case_id']]['memory_on'][item['repetition'] - 1] = delivered
        grouped_delivery = a.primary_interval([m for m in metadata if m['case_id'] in case_ids],
                                              delivery_scores, samples=10000, seed=20261024)
        group['non_delivery_group_uncertainty'] = {
            'planned_tasks': grouped_delivery['planned_tasks'], 'scenario_groups': grouped_delivery['scenario_groups'],
            'planned_episodes': len(cells), 'non_delivery_point': 1 - grouped_delivery['point_bounds']['a_lower'],
            'one_sided_95_upper': 1 - grouped_delivery['a_one_sided_95_lower'],
            'bootstrap_seed': 20261024, 'bootstrap_samples': 10000, 'method': grouped_delivery['method'],
            'scope': 'Operational non-delivery: unknown emission or missing answer is not a delivered answer.'}
        times, delivered_times, tokens = [], [], Counter()
        usage_requests = 0
        for cell_id in cells:
            row = results.get(cell_id, {})
            value = row.get('total_ns')
            if type(value) in (int, float) and 0 <= value < float('inf'):
                times.append(value / 1e9)
                if row.get('status') == 'completed':
                    delivered_times.append(value / 1e9)
            usage = row.get('usage')
            if isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ('prompt_tokens', 'completion_tokens')):
                tokens.update({k: usage[k] for k in ('prompt_tokens', 'completion_tokens')})
                usage_requests += 1
        def summary(values):
            return {'n': len(values), 'p50_seconds': a.quantile(values, .5) if values else None,
                    'p95_seconds': a.quantile(values, .95) if values else None}
        latencies.append({'model': group['model'], 'arm': group['arm'], 'planned': len(cells),
              'observed_all_statuses': summary(times), 'completed_only': summary(delivered_times),
              'scope': 'consumer total_ns: preparation, retrieval, generation and checks; no fabricated provider-only latency',
              'quantile_method': 'linear_interpolation_p_times_n_minus_one',
              'usage_requests': usage_requests, 'usage_missing_requests': len(cells) - usage_requests,
              'observed_tokens': dict(tokens)})
    accounting = values.get('accounting')
    if accounting is not None:
        require(accounting['schema'] == 'persistent-memory.volume.reporting-accounting.v1', 'accounting_scope')
        for key in ('conservative_debit_usd', 'usage_calculated_usd'):
            v = accounting.get(key)
            require(v is None or type(v) is str and Decimal(v).is_finite() and Decimal(v) >= 0, 'accounting_amount')
        require(accounting.get('actual_billed_usd') is None, 'invoice_not_established_by_this_report')
    costs = {'campaign_cap_usd': freeze['campaign_max_USD'], 'generation_cap_usd': freeze['generation_max_USD'],
             'judge_cap_usd': freeze['judge_max_USD'], 'prior_conservative_debit_usd': freeze['prior_debit_USD'],
             'conservative_debit_usd': accounting.get('conservative_debit_usd') if accounting else None,
             'usage_calculated_usd': accounting.get('usage_calculated_usd') if accounting else None,
             'usage_calculation_scope': accounting.get('usage_calculation_scope') if accounting else None,
             'usage_coverage_requests': accounting.get('usage_coverage_requests') if accounting else None,
             'actual_billed_usd': None, 'invoice_status': 'unknown', 'new_financial_engine': False}
    judging = Counter()
    for episode in episodes:
        js = judgments['judgments'].get(episode['cell_id'], {})
        generation = results.get(episode['cell_id'], {})
        eligible = (generation.get('status') == 'completed' and generation.get('provider_called') is True
                    and generation.get('response_model') == episode['model'] and isinstance(generation.get('body'), str)
                    and bool(generation['body'].strip()))
        labels = [a.bound_judgment(js.get(label), generation, episode['cell_id'], label) if eligible else None for label in ('A', 'B')]
        judging['planned_generation_episodes'] += 1
        if all(j is not None for j in labels):
            judging['two_complete_parseable_judges'] += 1
            if all(labels[0][k] is not None and labels[0][k] == labels[1][k] for k in ('success', 'critical_violation')):
                judging['concordant'] += 1
            else:
                judging['disagreement_or_undecidable'] += 1
        else:
            judging['missing_incomplete_or_invalid_judgment'] += 1
    judge_rows = [row for pair in judgments['judgments'].values() for row in pair.values()]
    require(type(judgments['planned_judge_requests']) is int
            and len(judge_rows) == judgments['planned_judge_requests'] <= 2 * episode_count,
            'normalized_planned_judge_denominator')
    generation_emissions = emission_counts(generations['results'].values())
    execution_confirmed_complete = bool(report['execution_complete'] and generation_emissions['unknown_emission'] == 0)
    report.update(development_only=config['development_only'], secondary_comparisons=secondaries,
        pass_three_by_model_arm=dict(pass3), primary_first_repetition_pairs=dict(Counter(
            a.outcome(p.get('memory_on'), p.get('memory_off')) for p in by_pair.values())),
        exploratory_families=family_rows, latencies_and_usage=latencies, costs=costs, judging_coverage=dict(judging),
        emission_accounting={'generation': generation_emissions,
                             'judges': emission_counts(judge_rows),
                             'judge_jobs_planned': judgments['planned_judge_requests'],
                             'judge_requests_not_planned_or_ineligible': 2 * episode_count - judgments['planned_judge_requests'],
                             'unknown_emissions_are_not_zero_emissions': True},
        qualification_requires_all_separate_gates=True,
        execution_confirmed_complete=execution_confirmed_complete,
        all_pre_registered_requirements_met=bool(execution_confirmed_complete and report['safety_and_technical_threshold_met']
            and report['primary']['absolute_quality_confirmed'] and report['primary']['differential_benefit_confirmed']),
        limits={'scenario_groups': groups, 'tasks_independent_claimed': False, 'AI_judges': 2, 'human_audits': 0,
                'technical_load_5000': 'actual 40-minute timeout; partial counts and phase unknown; not qualified',
                'scope': freeze['scope'], 'universal_production_guarantee': False},
        provenance={'reporting_manifest_sha256': pin, 'inputs': config['inputs'], 'analysis_sha256': ANALYSIS_SHA,
                    'bootstrap_primary_seed': 20261024, 'bootstrap_secondary_seeds': [20261025, 20261026]})
    require(sha(read_ref(root, config['inputs']['analysis'])) == ANALYSIS_SHA, 'analysis_changed_during_report')
    return report


def markdown(report, language):
    fr = language == 'fr'
    def yes(v):
        return ('oui' if v else 'non') if fr else ('yes' if v else 'no')
    def interval(values):
        return ' / '.join(f'{100 * n:.2f} %' for n in values)
    def amount(v):
        return ('inconnu' if fr else 'unknown') if v is None else str(v) + ' USD'
    primary = report['primary']
    lines = ['# ' + ('Mémoire persistante — résultats de validation' if fr else 'Persistent memory — validation results'), '']
    if report['development_only']:
        lines += ['**' + ('DONNÉES DEV SYNTHÉTIQUES — aucune performance réelle mesurée.' if fr else
                          'SYNTHETIC DEV DATA — no real performance measurement.') + '**', '']
    tasks, groups, episode_count = report['planned_tasks'], report['primary']['scenario_groups'], report['planned_episodes']
    formatted_episodes = f'{episode_count:,}'.replace(',', ' ') if fr else f'{episode_count:,}'
    lines += [(f'{tasks} tâches choisies, {groups} groupes de scénarios, trois répétitions et {formatted_episodes} épisodes prévus. Les tâches d’un même groupe ne sont pas indépendantes.' if fr else
               f'{tasks} selected tasks, {groups} scenario groups, three repetitions and {formatted_episodes} planned episodes. Tasks within a group are not independent.'), '',
              '| ' + ('Indicateur | Résultat |' if fr else 'Measure | Result |'), '|---|---|',
              f'| {"Réponses remises" if fr else "Answers delivered"} | {report["delivered"]} / {episode_count} |',
              f'| {"Épisodes non exécutés" if fr else "Episodes not executed"} | {report["not_executed"]} |',
              f'| {"Exécution complète confirmée" if fr else "Complete execution confirmed"} | {yes(report["execution_confirmed_complete"])} |',
              f'| {"Incidents critiques confirmés" if fr else "Confirmed critical incidents"} | {report["critical_violations_confirmed"]} |',
              f'| {"Réussite A, bornes conservatrices" if fr else "A success, conservative bounds"} | {interval([primary["point_bounds"]["a_lower"], primary["point_bounds"]["a_upper"]])} |',
              f'| {"Effet A−B, intervalle d’incertitude nominal 95 %" if fr else "A−B effect, nominal 95% uncertainty interval"} | {interval(primary["effect_uncertainty_interval_95"])} |',
              f'| {"Qualité absolue conforme" if fr else "Absolute quality requirement met"} | {yes(primary["absolute_quality_confirmed"])} |',
              f'| {"Bénéfice différentiel confirmé" if fr else "Differential benefit confirmed"} | {yes(primary["differential_benefit_confirmed"])} |',
              f'| {"Exécution, sécurité et non-remise conformes" if fr else "Execution, safety and delivery requirements met"} | {yes(report["safety_and_technical_threshold_met"])} |', '',
              ('Le calcul conserve les inconnus et tous les épisodes prévus. Le bootstrap apparié rééchantillonne les groupes dans chaque famille (10 000 tirages); il ne transforme pas les répétitions en tâches indépendantes.' if fr else
               'The calculation retains unknown outcomes and every planned episode. The paired bootstrap resamples scenario groups within each family (10,000 draws); repetitions do not become independent tasks.'), '',
              '## ' + ('Comparaisons secondaires' if fr else 'Secondary comparisons'), '']
    for item in report['secondary_comparisons']:
        s = item['statistics']
        lines += [f'- {item["model"]}, {item["arm_a"]} − {item["arm_b"]}: {s["planned_tasks"]} ' +
                  ('tâches du sous-ensemble gelé' if fr else 'tasks from the frozen subset') +
                  f'; 95 %: {interval(s["effect_uncertainty_interval_95"])}; seed {s["bootstrap_seed"]}.']
    lines += ['', '## ' + ('Stabilité et première répétition' if fr else 'Stability and first repetition'), '',
              ('`pass^3` exige trois réussites confirmées; un inconnu reste visible. Les comptes ci-dessous portent sur des tâches.' if fr else
               '`pass^3` requires three confirmed successes; unknown outcomes remain visible. Counts below are task counts.'), '',
              '| Modèle / bras | 3/3 | ' + ('Échec | Inconnu |' if fr else 'Failure | Unknown |'), '|---|---:|---:|---:|']
    for key, counts in sorted(report['pass_three_by_model_arm'].items()):
        lines += [f'| {key} | {counts.get("success", 0)} | {counts.get("failure", 0)} | {counts.get("unknown", 0)} |']
    pairs = report['primary_first_repetition_pairs']
    lines += ['', ('Première répétition A/B : ' if fr else 'First A/B repetition: ') +
              ', '.join(f'{key}={pairs.get(key, 0)}' for key in ('gain', 'loss', 'tie_success', 'tie_failure', 'unknown')) + '.', '',
              '## ' + ('Émissions et non-remise' if fr else 'Emissions and non-delivery'), '',
              '| ' + ('Phase | Émissions confirmées | Émission incertaine | Non-émis confirmés | Jamais exécutés |' if fr else
                       'Phase | Confirmed emissions | Unknown emission | Confirmed not emitted | Not executed |'), '|---|---:|---:|---:|---:|']
    for phase in ('generation', 'judges'):
        e = report['emission_accounting'][phase]
        lines += [f'| {phase} | {e["confirmed_emitted"]} | {e["unknown_emission"]} | {e["confirmed_not_emitted"]} | {e["not_executed"]} |']
    lines += ['', ('Une émission incertaine conserve ce statut et son exposition financière; elle ne compte pas comme zéro émission. Les épisodes jamais exécutés sont un sous-ensemble, pas une colonne à additionner.' if fr else
                    'An uncertain emission retains that status and its financial exposure; it is not counted as zero emissions. Episodes not executed are a subset, not an additional column to sum.'), '',
              '| Modèle / bras | ' + ('Tâches / groupes | Non-remise | Borne supérieure unilatérale95 % |' if fr else
                                      'Tasks / groups | Non-delivery | One-sided95% upper bound |'), '|---|---:|---:|---:|']
    for item in report['by_model_arm']:
        q = item['non_delivery_group_uncertainty']
        lines += [f'| {item["model"]} / {item["arm"]} | {q["planned_tasks"]} / {q["scenario_groups"]} | {100*q["non_delivery_point"]:.3f} % | {100*q["one_sided_95_upper"]:.3f} % |']
    lines += ['', ('Bornes obtenues par le bootstrap groupé gelé, 10000tirages et seed20261024, en conservant les trois répétitions. Les Wilson descriptifs de première répétition restent disponibles séparément dans le JSON.' if fr else
                    'Bounds use the frozen grouped bootstrap, 10,000 draws and seed20261024, keeping all three repetitions together. Descriptive first-repetition Wilson bounds remain separate in the JSON.'), '',
              '## ' + ('Familles — lecture exploratoire' if fr else 'Families — exploratory results'), '',
              '| ' + ('Famille | Tâches | Bornes de l’effet |' if fr else 'Family | Tasks | Effect bounds |'), '|---|---:|---|']
    for item in report['exploratory_families']:
        lines += [f'| {item["family"]} | {item["planned_tasks"]} | {interval(item["point_effect_bounds"])} |']
    lines += ['', '## ' + ('Latences observées' if fr else 'Observed latency'), '',
              '| Modèle / bras | N | p50 (s) | p95 (s) |', '|---|---:|---:|---:|']
    for item in report['latencies_and_usage']:
        q = item['completed_only']
        fmt = lambda n: '—' if n is None else f'{n:.3f}'
        lines += [f'| {item["model"]} / {item["arm"]} | {q["n"]} | {fmt(q["p50_seconds"])} | {fmt(q["p95_seconds"])} |']
    lines += ['', ('Temps total du consommateur pour les réponses complètes disposant d’une trace; préparation, récupération et contrôles compris. Les données absentes ne sont pas remplacées par zéro.' if fr else
                  'Total consumer time for completed answers with timing data, including preparation, retrieval and checks. Missing timings are not replaced with zero.'), '',
              '## ' + ('Coûts et portée' if fr else 'Costs and scope'), '',
              ('Plafond de génération : ' if fr else 'Generation cap: ') + amount(report['costs']['generation_cap_usd']) + '; ' +
              ('plafond des juges : ' if fr else 'judge cap: ') + amount(report['costs']['judge_cap_usd']) + '.',
              ('Débit conservateur rapproché : ' if fr else 'Reconciled conservative debit: ') + amount(report['costs']['conservative_debit_usd']) + '; ' +
              ('coût calculé depuis l’usage : ' if fr else 'cost calculated from reported usage: ') + amount(report['costs']['usage_calculated_usd']) + '; ' +
              ('facture : inconnue.' if fr else 'invoice: unknown.'), '',
              ('Deux juges IA, aucun audit humain; leurs erreurs peuvent être corrélées. Le test technique à 5 000 sources a atteint sa borne de 40 minutes : cette charge n’est pas qualifiée. Les résultats concernent le composant public et le consommateur portable exercés, sans certification de toute la production Hermes.' if fr else
               'Two AI judges, no human audit; their errors may be correlated. The technical test at 5,000 sources reached its 40-minute limit: that load is not qualified. Results cover the public component and the exercised portable consumer, without certifying the entire Hermes production system.'), '',
              ('Identifiants, états de chaque épisode, sources et SHA256 figurent dans REPORT.json et MANIFEST.json.' if fr else
               'Episode IDs, individual outcomes, source references and SHA256 pins are available in REPORT.json and MANIFEST.json.'), '']
    return '\n'.join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--manifest-sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    report = build_report(args.manifest, args.manifest_sha256)
    args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
    outputs = {'REPORT.json': encode(report), 'REPORT.fr.md': markdown(report, 'fr').encode(),
               'REPORT.en.md': markdown(report, 'en').encode()}
    for name, body in outputs.items():
        (args.output / name).write_bytes(body)
    manifest = {'schema': 'persistent-memory.volume.reporting-artifacts.v1',
                'reporter_sha256': sha(Path(__file__).read_bytes()), 'analysis_sha256': ANALYSIS_SHA,
                'input_manifest_sha256': args.manifest_sha256,
                'files': {name: {'bytes': len(body), 'sha256': sha(body)} for name, body in outputs.items()}}
    (args.output / 'MANIFEST.json').write_bytes(encode(manifest))
    print(json.dumps({'generated': str(args.output), 'development_only': report['development_only'],
                      'planned_episodes': report['planned_episodes'], 'not_executed': report['not_executed'],
                      'provider_calls': 0, 'site_changes': False}))


if __name__ == '__main__':
    main()
