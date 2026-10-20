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

## Reproduce the comparison / Reproduire la comparaison

The same example can also execute an explicitly defined **key-value cache without
dependency tracking** alongside the core. This is a small illustrative reference,
not a competitor evaluation or a claim about every RAG system. Both branches
receive the same source facts, the same explicitly rebuilt brief text, source
withdrawal and restoration of their pre-withdrawal content snapshot.

Le même exemple peut exécuter un **cache clé-valeur sans suivi des dépendances**
en parallèle du noyau. Cette référence minimale décrit un contrat précis ; elle
ne représente ni un concurrent, ni tous les systèmes RAG. Les deux branches
reçoivent les mêmes faits, le même texte de résumé reconstruit explicitement,
le retrait de la source et la restauration de leur contenu antérieur au retrait.

```sh
.venv/bin/python examples/portfolio_demo.py --compare \
  --directory /tmp/persistent-memory-atlas-comparison-new \
  --output /tmp/persistent-memory-atlas-comparison-new.json
```

Without `--compare`, the original five-event trace format remains unchanged.
With it, the new `persistent-memory.portfolio-demo.comparison.v1` envelope contains
the actual original `core_trace`, three `cases`, all reference operation receipts,
shared fixture inputs and their digest, the example digest, a digest of the
reference receipts and checked comparison invariants. Each reference receipt
records the actual operation, its inputs, result and resulting state digest.
Observations are captured while the operations run, not reconstructed from
expected answers afterwards. No existing recorded portfolio trace is overwritten.

Sans `--compare`, le format original à cinq événements est conservé. L'option
produit une enveloppe `persistent-memory.portfolio-demo.comparison.v1` contenant
la vraie `core_trace`, trois `cases`, les reçus des opérations du cache, les mêmes
entrées fictives, leurs empreintes et les invariants vérifiés. Chaque reçu donne
l'opération réelle, ses entrées, son résultat et l'empreinte de l'état obtenu.
Les observations sont capturées pendant l'exécution, sans fabriquer les sorties
à partir des résultats attendus. La trace historique du portfolio est préservée.

| Case / Cas | Reference and core / Référence et noyau |
| --- | --- |
| Correction, before rebuild / avant reconstruction | Both receive Monday. The cache still returns its stored Friday brief; the core denies its old exact-version brief. / Les deux reçoivent lundi ; le cache conserve le résumé vendredi, le noyau refuse l'ancien résumé lié à la version remplacée. |
| Correction, after rebuild / après reconstruction | Both receive and return the same Monday brief. The cache is correct after explicit rebuilding. / Les deux reçoivent et retournent le même résumé lundi ; le cache est corrigé par la reconstruction explicite. |
| Withdrawal / Retrait | The cache removes the requested date key; its separately stored brief remains. The core denies the date and the brief through its declared dependencies. / Le cache supprime la date demandée, mais conserve le résumé séparé ; le noyau refuse les deux via les dépendances déclarées. |
| Restore / Restauration | The cache reloads its actual JSON snapshot, including date and brief. The core restores content against its separately retained current authority and freshness witness; withdrawn date and brief remain denied. / Le cache recharge son vrai snapshot JSON, date et résumé inclus ; le noyau confronte le contenu à son autorité et son témoin courants conservés à part, et refuse encore date et résumé retirés. |

The cache stores content in a Python dictionary and writes/reads a real JSON
snapshot. Updating or deleting a key affects only that key. Declared dependency
inputs are present in receipts but are not tracked or revalidated by the cache.
It has no separate revocation authority or freshness witness. The core retains
both outside the content backup. This architectural difference is part of the
comparison, not a hidden assumption. Explicit cache invalidation or rebuilding
can address stale content; the reference intentionally implements neither an
automatic dependency policy nor a persistent revocation authority. The independent
French project-language fact remains readable in both branches after every case.
There is no comparison of speed, durability, reliability or model quality.

Le cache conserve le contenu dans un dictionnaire Python et écrit/relit un vrai
snapshot JSON. Une écriture ou suppression ne modifie que la clé visée. Les
dépendances reçues figurent dans les reçus mais ne sont ni suivies ni revalidées.
Le cache ne possède ni autorité de retrait séparée ni témoin de fraîcheur ; le
noyau les conserve hors de la sauvegarde de contenu. Cette différence
d'architecture est explicite. Une invalidation ou reconstruction du cache peut
corriger du contenu obsolète ; cette référence ne met en œuvre ni politique
automatique de dépendances ni autorité persistante de retrait. Le français,
langue de communication du projet, reste lisible dans les deux branches après
chaque cas. Aucune mesure comparative de vitesse, durabilité, fiabilité ou qualité
de modèle n'est revendiquée.

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
