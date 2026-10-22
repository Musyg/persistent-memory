# Configuration transformation / Transformation des configurations

This is a file transformation, not a new experiment runner. It opens only the two public synthetic inputs named below and writes inactive local files. It performs no import of the generation modules, provider operation, scoring, retry or network access. Run it only after validating the archive's published hashes. Choose one actual block ID from the public plan projection; do not use an operational grant.

Cette transformation de fichiers ne lance aucun essai. Elle lit uniquement les deux fichiers synthétiques publics indiqués et écrit des fichiers locaux inactifs, sans importer les modules de génération, appeler un fournisseur, calculer un score ou accéder au réseau. Vérifier au préalable les empreintes de l'archive. Choisir un identifiant de bloc réel dans la projection publique du plan ; ne pas reprendre une autorisation d'exploitation.

From `REPLAY/`, replacing `G0001` with the selected public block ID / Depuis `REPLAY/`, remplacer `G0001` par l'identifiant public choisi :

```sh
python3 -I -B - ../DATA/CASES.json ../DATA/GENERATION-PLAN-PROJECTION.json G0001 work <<'PY'
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

case_path, plan_path, selected, destination = sys.argv[1:]
case_raw, plan_raw = Path(case_path).read_bytes(), Path(plan_path).read_bytes()
case_file, plan = json.loads(case_raw), json.loads(plan_raw)
assert plan['schema'] == 'persistent-memory.volume.phase-plan.v1'
assert plan['purpose'] == 'generation'
assert plan['analysis_projection'] is True and plan['executable'] is False
blocks = [b for b in plan['blocks'] if b['block_id'] == selected]
assert len(blocks) == 1
block = blocks[0]
cells = block['budget']['cells']
assert 1 <= len(cells) <= 3
assert all(set(c) == {'cell_id', 'task_id', 'stage', 'arm'} for c in cells)
assert all(c['stage'] in ('rep1', 'rep2', 'rep3') for c in cells)
assert all(c['arm'] in ('memory_on', 'memory_off', 'simple_baseline') for c in cells)
assert len({c['cell_id'] for c in cells}) == len(cells)
assert all(type(v) is str and 0 < len(v) <= 128 for c in cells for v in c.values())
ids = {c['task_id'] for c in cells}
cases = [c for c in case_file['cases'] if c['case_id'] in ids]
assert len(cases) == len(ids) == len({c['case_id'] for c in cases})
models = {
    'gpt-6-luna': ('volume_luna6_none_v1', 'none', '0.0021504'),
    'gpt-6.1-sol': ('volume_sol61_low_v1', 'low', '0.043008'),
}
model = block['budget']['model']
profile_id, effort, unit = models[model]
encode = lambda v: (json.dumps(v, ensure_ascii=False, sort_keys=True,
    indent=2, allow_nan=False) + '\n').encode('utf-8')
sha = lambda raw: hashlib.sha256(raw).hexdigest()
packet = {'schema': 'persistent-memory.public-replay.inputs.v1',
    'synthetic': True, 'development_only': False,
    'budget': {'top_k': 5, 'max_context_chars': 2000, 'candidate_limit': 100},
    'cases': cases}
packet_raw = encode(packet)
profile = {'schema_version': 1, 'profile': profile_id, 'purpose': 'generation',
    'dataset_sha256': sha(packet_raw), 'cells': cells, 'max_requests': len(cells),
    'wall_seconds': 300, 'per_request_usd': unit,
    'max_total_usd': str(Decimal(unit) * len(cells))}
budget = {**profile, 'authorized_for_execution': False, 'price_verified': False,
    'tokenizer_bound_verified': False, 'reasoning_total_bound_verified': False,
    'model': model, 'endpoint': 'https://api.openai.com/v1/chat/completions',
    'request_options': {'reasoning_effort': effort}, 'response_models': [model],
    'input_tokens_per_request': 11264, 'output_tokens_per_request': 2048,
    'full_request_bytes': 10240, 'message_bytes': 10240,
    'framing_token_allowance': 1024, 'timeout_seconds': 90, 'expires_at_epoch': 0}
selection = {'new_run_only': True, 'historical_results_unchanged': True,
    'source_cases_sha256': sha(case_raw), 'source_public_plan_sha256': sha(plan_raw),
    'selected_block_id': selected, 'selected_cells': cells,
    'new_packet_sha256': sha(packet_raw)}
output = Path(destination)
output.mkdir(mode=0o700, parents=False, exist_ok=False)
for name, raw in [('inputs.json', packet_raw), ('profile.json', encode(profile)),
    ('budget.INACTIVE.json', encode(budget)), ('selection.json', encode(selection))]:
    with (output / name).open('xb') as stream:
        stream.write(raw)
print('Inactive configuration only:', output, 'maximum calls:', len(cells))
PY
```

`development_only: false` means the selected cases originate in the public study, **not** that the new answers are historical results or have passed. `selection.json` records the new packaging and source hashes. Keep the new responses separate. For the disposable DEV fixtures, copy `DEV/inputs.json`, one `DEV/*-profile.json` and its matching `DEV/*-budget.INACTIVE.json` into a new `work/` directory instead; those inputs retain `development_only: true`.

`development_only: false` signifie que les cas viennent de l'étude publique, **pas** que les nouvelles réponses sont historiques ou validées. `selection.json` conserve les SHA des sources et du nouveau paquet. Garder les nouvelles réponses séparées. Pour les fixtures jetables, copier plutôt `DEV/inputs.json`, un `DEV/*-profile.json` et le budget `DEV/*-budget.INACTIVE.json` correspondant dans un nouveau répertoire `work/` ; ces entrées restent `development_only: true`.

The inactive configuration deliberately fails `Budget._init_volume` until the operator performs the documented review and activation. Key spellings and required fixed values match that existing method, including **`expires_at_epoch`**, generation-only caps and Decimal strings. Changing a selection requires a new input pin, profile, budget, output directory and ledger; no automatic loop over the campaign is provided.

La configuration échoue volontairement dans `Budget._init_volume` tant que l'opérateur n'a pas effectué la revue et l'activation décrites. Les noms et valeurs requis reprennent la méthode existante, notamment **`expires_at_epoch`**, les plafonds propres à la génération et les montants en chaînes décimales. Changer de sélection exige un nouveau pin d'entrée, profil, budget, répertoire de sortie et ledger ; aucune boucle automatique sur la campagne n'est fournie.
