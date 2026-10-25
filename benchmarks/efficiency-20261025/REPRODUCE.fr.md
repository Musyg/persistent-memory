# Reproduire le cycle incrémental sous Linux

[English](REPRODUCE.md) · [Étude](README.fr.md) · [Protocole](PROTOCOL.json) · [Empreintes des sources](SOURCE-PINS.json)

Utiliser un checkout complet du **commit de publication qui contient cette page**, avec Python et SQLite FTS5. Le benchmark doit avoir l’empreinte `a2cfda65d6df85f76670af5efb413fc3f0d3d776cd8324e5251cf3b05bfa1b02`. Le tag et le sdist a4 contiennent l’ancienne CLI, dépourvue de `--volume-incremental-batch`. Copier l’identifiant complet du commit depuis son lien permanent GitHub, puis vérifier le checkout avant l’exécution.

La mesure de laboratoire archivée utilise des wheels communs 0.3.0a2 et trois modules explicitement sélectionnés par bras. Pour une nouvelle comparaison, le wheel public du noyau a4 et celui du registre 0.2.0a2 peuvent fournir un support commun neuf. Cela crée un nouvel environnement ; cela ne reconstruit pas les octets des anciens wheels et ne mesure pas les distributions a4 installées. Récupérer les wheels avant d’entrer dans l’enveloppe de mesure sans réseau et vérifier les sommes de contrôle des actifs sélectionnés.

Créer un seul environnement virtuel neuf pour l'ensemble des six cellules. Définir `CHECKOUT`, `ENV`, `CORE_WHEEL` et `REGISTRY_WHEEL` avec ses propres chemins absolus. Dans l'unité de mesure décrite ci-dessous, installer les dépendances une seule fois, sans compilation anticipée. Avant chaque cellule, définir `ARM` à `A` ou `B`, appliquer les trois modules correspondants et vérifier leurs imports dans un processus neuf avec le contrôle ci-dessous.

```sh
python3 -m venv "$ENV"
"$ENV/bin/python" -I -B -m pip install --no-compile --no-index --no-deps \
  "$CORE_WHEEL" "$REGISTRY_WHEEL"
```

Le contrôle de liaison ci-dessous agit uniquement dans ce nouvel environnement. Il sélectionne les trois modules déjà publics, vérifie leurs octets, les importe réellement et refuse tout bytecode préexistant. Il ne crée aucun stockage mémoire. Conserver sa sortie JSON avec les preuves de la cellule.

```sh
"$ENV/bin/python" -I -B - "$CHECKOUT" "$ARM" <<'PY'
import hashlib, importlib, json, pathlib, subprocess, sys, sysconfig
checkout, arm = pathlib.Path(sys.argv[1]).resolve(), sys.argv[2]
versions = {
 'A': ('1554beda0ef3e57621eca8974c197514302f369e', [
  '35dd711acb3dd16e97237721b7332a73b4d4822a88c227fc445722256cd5cecb',
  'f6f5284dcdcd9f6530ff34973c2b453f7dc5f0d5b877a134f709ad3e03454729',
  '201795feebd7a508cbea7dcc7638341f0da946c0288017c80d55f50a34826dee']),
 'B': ('14ec99ca3eb12f801b352101d2e67508cb187de9', [
  '76dba2b15a4d33005d07abcd08306199fffa2bc2ff7b3cbe268590c7776878ce',
  '4a5d16812a68d89e47b0274d432da9816876ae2ed73409131a09495b006c103d',
  '2af69d57e66184388e0736702ead3d55575ce69c4924ea7548eeb957f4388801'])}
commit, pins = versions[arm]
names = ['core.py', 'typed_memory.py', 'typed_protocol.py']
package = pathlib.Path(sysconfig.get_paths()['purelib']).resolve() / 'hermes_memory'
assert sys.prefix != sys.base_prefix and package.is_relative_to(pathlib.Path(sys.prefix).resolve())
assert not any((package / '__pycache__').glob('*.pyc'))
for name, pin in zip(names, pins):
    raw = subprocess.check_output(['git', '-C', str(checkout), 'show',
                                   commit + ':src/hermes_memory/' + name])
    assert hashlib.sha256(raw).hexdigest() == pin
    (package / name).write_bytes(raw)
loaded = {}
for name, pin in zip(names, pins):
    module = importlib.import_module('hermes_memory.' + name[:-3])
    path = pathlib.Path(module.__file__).resolve()
    assert path == package / name and hashlib.sha256(path.read_bytes()).hexdigest() == pin
    assert not pathlib.Path(module.__cached__).exists()
    loaded[name] = pin
from hermes_memory import typed_memory, typed_protocol
assert typed_memory.CORE_SHA == pins[0] and typed_protocol.R3_SHA == pins[1]
assert not any((package / '__pycache__').glob('*.pyc'))
runner = checkout / 'benchmarks/run_benchmark.py'
assert hashlib.sha256(runner.read_bytes()).hexdigest() == 'a2cfda65d6df85f76670af5efb413fc3f0d3d776cd8324e5251cf3b05bfa1b02'
print(json.dumps({'arm': arm, 'module_commit': commit, 'loaded_sha256': loaded,
                  'CORE_SHA': typed_memory.CORE_SHA, 'R3_SHA': typed_protocol.R3_SHA,
                  'bytecode_absent': True, 'checkout_commit': subprocess.check_output(
                  ['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()}))
PY
```

Exécuter les six cellules à la suite dans l’ordre **A, B, B, A, A, B**, chacune avec un processus, une base et un répertoire RAM neufs. Toute la séquence doit tenir dans une seule unité transitoire de 1 200 secondes : quota CPU de 50 %, mémoire de 1 Gio, swap désactivé, 64 tâches au maximum, réseau privé et interdiction d’acquérir de nouveaux privilèges. Relever les limites effectives de l’unité et du cgroup pendant son activité. Chaque enfant dispose de 180 secondes. La création de l’environnement virtuel et l’installation hors ligne font partie de la limite globale de 1 200 secondes. Les wheels doivent être disponibles avant l’entrée dans l’unité sans réseau. Ces limites appartiennent au protocole.

Dans cette enveloppe, créer un répertoire privé neuf `CELL_RAM` sous `/dev/shm` et un répertoire de sortie ordinaire `CELL_OUTPUT`. Exécuter une fois le Python sélectionné :

```sh
TMPDIR="$CELL_RAM" timeout --signal=KILL 180s \
  "$ENV/bin/python" -I -B "$CHECKOUT/benchmarks/run_benchmark.py" \
  --documents 1000 --repetitions 50 --seed 20261021 \
  --volume-progress "$CELL_OUTPUT/progress.json" --volume-incremental-batch 10 \
  > "$CELL_OUTPUT/result.json" 2> "$CELL_OUTPUT/stderr.log"
```

Conserver le code de sortie, les fichiers produits, les timeouts et les cellules non lancées. Attendre la fin de chaque enfant avant de supprimer uniquement son répertoire RAM. Ne remplacer aucune cellule en échec, ne pas relancer automatiquement et ne pas augmenter les plafonds. Les dix nouvelles sources sont interrogées une fois chacune dans l’ordre d’admission, puis 40 requêtes proviennent de tirages sur le corpus initial avec la graine fixée. Le programme de requêtes a pour empreinte `43246effb8574adaeb53eb0dff4984a1b2845f7bd2acbe8b1c204bb678c57bfe`.

Comparer séparément le chargement initial et les phases marginales, après contrôle de tous les oracles. Cinquante recherches dans une cellule ne sont pas cinquante répétitions indépendantes. Le cycle comprend les lectures de validation, le retrait, la synchronisation, un témoin valide et la télémétrie. Le cache n’est pas contrôlé, le surcoût de télémétrie n’est pas isolé, le coût d’infrastructure et l’énergie restent inconnus. Les nouvelles durées dépendront de l’hôte et de sa charge. Aucun service de production, souvenir privé, appel fournisseur ou déploiement n’intervient.
