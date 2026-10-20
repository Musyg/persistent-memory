# Reproduce the portfolio demonstration / Reproduire la démonstration

This five-step example calls the installed **public memory core 0.3.0a2**. It creates
synthetic project evidence, derives a brief with exact parent versions, corrects
a deadline with compare-and-swap, withdraws it, and restores an older content
snapshot against the retained current authority. An unrelated language preference
remains readable. There is no model, account, network request or private data.

Cet exemple utilise le **noyau public 0.3.0a2 installé** : deux preuves fictives,
un brief avec ses dépendances exactes, une correction avec version attendue,
un retrait, puis une ancienne sauvegarde confrontée à l'autorité courante.
La préférence de langue indépendante reste lisible. Aucun modèle, compte,
appel réseau ou contenu privé n'intervient.

## Run on Linux / Exécuter sous Linux

From a source checkout containing this example, use Python 3.11+ and a new state
directory and output file. Installation may access your configured package index;
the example itself uses only the standard library and the installed memory core.

Depuis le dépôt contenant cet exemple, utiliser Python 3.11+, un nouveau dossier
d'état et un nouveau fichier de sortie. L'installation peut consulter l'index de
paquets configuré ; l'exemple lui-même n'effectue aucun appel réseau.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python examples/portfolio_demo.py \
  --directory /tmp/persistent-memory-atlas-new \
  --output /tmp/persistent-memory-atlas-trace-new.json
```

The script checks the installed version and the SHA-256 of its actual imported
`core.py`. It refuses an existing state directory or trace file. Choose new names
for another run. It never deletes a prior run. The trace records the example and
module hashes, base library commit, generation time, immutable references, raw
read decisions, dependency graphs and checked Boolean invariants. It contains no
hostnames, absolute paths or user identity. A portfolio reader can display this
captured trace; changing a browser view does not execute a new memory operation.

Le script vérifie la version installée et le SHA-256 du `core.py` réellement
importé. Il refuse un dossier ou un fichier existant ; choisir de nouveaux noms
pour une autre exécution. La trace contient les empreintes du script et du module,
le commit de référence de la bibliothèque, l'heure, les références immuables,
les décisions brutes, les graphes de dépendances et les invariants vérifiés.
Elle ne contient ni nom de machine, ni chemin absolu, ni identité personnelle.
Le lecteur du portfolio affiche cette trace ; naviguer entre les étapes ne lance
pas de nouvelle opération mémoire.

| Step / Étape | Observation |
| --- | --- |
| 1. Admit / Enregistrer | Friday deadline and French communication preference are readable. / Date vendredi et préférence française lisibles. |
| 2. Derive / Dériver | The brief names the exact two parent versions. / Le brief référence les deux versions sources exactes. |
| 3. Correct / Corriger | CAS changes Friday to Monday. The old brief is denied **before** replacement; a new brief survives a storage reopen. / CAS remplace vendredi par lundi ; l'ancien brief est refusé **avant** son remplacement ; le nouveau reste lisible après réouverture. |
| 4. Withdraw / Retirer | Current deadline and dependent brief are denied; the language preference remains readable. / Date et brief dérivé refusés ; langue indépendante préservée. |
| 5. Restore / Restaurer | An old content backup starts quarantined. After current-authority verification, withdrawn versions stay denied and the independent control is readable. / L'ancienne sauvegarde est mise en quarantaine, puis vérifiée contre l'autorité courante ; les versions retirées restent refusées et le contrôle indépendant reste lisible. |

## Scope / Périmètre

This is a deterministic application example and recorded execution, **not** a
model reasoning demonstration, semantic truth verifier or statistical benchmark.
Storage reopening does not simulate a process crash or hardware failure.
The dependency graph covers declared dependencies. Revocation controls future
reads through the library; it is not physical erasure or model unlearning.
Keep authority and freshness witness outside content snapshots. Rolling every
trusted component back together is outside this recovery guarantee.

Il s'agit d'un exemple déterministe et d'une exécution enregistrée, **pas** d'une
démonstration de raisonnement d'un modèle, d'une validation de vérité ou d'un
benchmark statistique. La réouverture ne simule pas une panne de processus ou de
matériel. Le graphe couvre les dépendances déclarées. Le retrait contrôle les
lectures futures par cette bibliothèque, sans promettre effacement physique ou
désapprentissage. L'autorité et son témoin de fraîcheur doivent être conservés
hors des sauvegardes de contenu. Leur retour arrière coordonné dépasse cette garantie.

See / Voir [recovery contract](RECOVERY.md) and [public API](API.md).
