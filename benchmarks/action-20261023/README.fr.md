# Transfert de mémoire vers des fichiers vérifiés

[English](README.md) · [Fixture synthétique](FIXTURE.json) · [Plan des cellules](PLAN.json)

L’étude à paramètres nouveaux est clôturée : **486 résultats conformes, 89 actions erronées et un inconnu sur 576 appels**. Les bras utilisant la mémoire dépassent le bras sans mémoire sur ces tâches synthétiques. La mémoire typée ne dépasse pas la référence de recherche lexicale avec contrôle des versions.

## Résultats à paramètres nouveaux

72 appels par ligne. P2 termine 575 appels ; un appel Luna sans mémoire reçoit HTTP 500 et reste inconnu. Aucun refus de schéma.

| Modèle | Bras | Conforme | Erroné | Inconnu |
| --- | --- | ---: | ---: | ---: |
| GPT-6 Luna | Mémoire typée | 66 | 6 | 0 |
| GPT-6 Luna | Recherche lexicale avec contrôle des versions | 67 | 5 | 0 |
| GPT-6 Luna | Historique autorisé | 66 | 6 | 0 |
| GPT-6 Luna | Sans mémoire | 35 | 36 | 1 |
| GPT-6.1 Sol | Mémoire typée | 72 | 0 | 0 |
| GPT-6.1 Sol | Recherche lexicale avec contrôle des versions | 72 | 0 | 0 |
| GPT-6.1 Sol | Historique autorisé | 72 | 0 | 0 |
| GPT-6.1 Sol | Sans mémoire | 36 | 36 | 0 |
| **Total** | | **486** | **89** | **1** |

Chez Luna, la mémoire typée gagne 41,67 à 43,06 points sur le bras sans mémoire, selon l’issue de l’inconnu ; intervalle nominal à 95 % du bootstrap par groupes : +25,00 à +52,78 points. Sol gagne 50 points, avec un intervalle dégénéré [50, 50] dans ces strates synthétiques : aucune certitude universelle. Mémoire typée contre lexical : −1,39 point chez Luna, intervalle [−4,17 ; 0] ; égalité chez Sol. Le transfert est utile sur ce jeu, sans domination générale démontrée.

Rapport natif qualifié. Registry vérifie indépendamment 576 cas d’autorité courante sur 24 partitions et relit 575 résultats fichiers disponibles : 486 réussites, 89 échecs et un inconnu conservés. Les 13 672 fichiers historiques restent inchangés. [Observations de confirmation](confirmation/OBSERVATIONS.json) · [Résultat natif](confirmation/RESULT.json) · [Protocole](confirmation/PROTOCOL.md).

## Étude initiale : résultat négatif conservé

Première étude clôturée : **45 résultats fichiers conformes sur 576 appels modèles (7,8 %)**. Tous les P2 sont terminés ; aucun résultat inconnu. Bilan : 493 refus de schéma et 38 suspensions erronées acceptées. Aucun avantage mémoire démontré.

72 appels par ligne. Refus de schéma : enveloppe rejetée par l’hôte, actions non validées.

| Modèle | Bras | Conforme | Refus de schéma | Suspension erronée |
| --- | --- | ---: | ---: | ---: |
| GPT-6 Luna | Mémoire typée | 1 | 69 | 2 |
| GPT-6 Luna | Recherche lexicale avec contrôle des versions | 1 | 65 | 6 |
| GPT-6 Luna | Historique autorisé | 3 | 67 | 2 |
| GPT-6 Luna | Sans mémoire | 2 | 64 | 6 |
| GPT-6.1 Sol | Mémoire typée | 10 | 56 | 6 |
| GPT-6.1 Sol | Recherche lexicale avec contrôle des versions | 9 | 59 | 4 |
| GPT-6.1 Sol | Historique autorisé | 12 | 60 | 0 |
| GPT-6.1 Sol | Sans mémoire | 7 | 53 | 12 |
| **Total** | | **45** | **493** | **38** |

L’interface était sous-spécifiée : clé `schema` obligatoire jamais nommée explicitement, identifiants des sources sélectionnées absents de la mémoire présentée. Des demandes autosuffisantes ont aussi été suspendues inutilement. Ces défauts motivent une correction. Sources, réponses et scores initiaux restent figés.

Registry a relu hors ligne les 576 résultats sur 24 partitions : 45 réussites, 531 échecs, 12 802 fichiers historiques inchangés.

## Méthode et contrôles

24 mondes synthétiques : 12 français, 12 anglais, paramètres distincts dans 12 structures. Familles : procédures, corrections, retraits et demandes autosuffisantes. Deux modèles, quatre bras, trois répétitions : 576 appels, pas des capacités indépendantes.

Mémoire typée, recherche lexicale avec contrôle des versions et historique autorisé partagent les contrôles de version, retrait, périmètre et admissibilité. L’historique masque les contenus remplacés, retirés ou inéligibles ; le quatrième bras reçoit la tâche seule. Plafond commun : cinq éléments, 2 000 caractères, historique intégral ; prompts et dépenses non égalisés.

Le processus P1 enregistre les observations de manière déterministe, puis se termine. Un nouveau processus P2 ouvre ensuite la mémoire et obtient une proposition JSON : deux écritures CSV/JSON maximum sur des cibles autorisées. L’autorité est revérifiée avant toute écriture dépendante. Après sa sortie, P3 relit les fichiers : attentes indépendantes cachées au modèle, octets exacts et sémantique JSON/CSV. Un contrôle positif obligatoire empêche de réussir en bloquant tout. Le test porte sur le transfert, pas l’apprentissage autonome.

## Reproduction, coût et calibration

Rejouer sous Linux : deux paquets, fixture et plan vérifiés par empreinte, CLI existant. Commit initial : `a67c611fbabc75f31a87bc2c834740dd51414080`. Deux environnements ont chacun passé 12 tests applicatifs, 192 cellules simulées et quatre tests client/budget simulés : raccordement uniquement.

Depuis la racine du dépôt, dans un environnement Linux neuf, reproduire le premier rapport hors ligne :

```sh
python -m pip install . ./packages/policy-registry
study=benchmarks/action-20261023
obs="$study/initial/OBSERVATIONS.json"
obs_sha=$(sha256sum "$obs" | cut -d' ' -f1)
test "$obs_sha" = 28d14498adce39ef47c67833e17e8444061b28af24e436632012ff85bd1a8808 || exit 1
python -I -B benchmarks/run_benchmark.py --action-report "$obs" --action-report-sha256 "$obs_sha"
```

L’empreinte porte sur **tout le fichier brut OBSERVATIONS.json**, pas sur des lignes choisies ou un champ interne. Preuves : [observations initiales](initial/OBSERVATIONS.json), [résultat initial](initial/RESULT.json), [état de calibration](calibration/READINESS.json), [provenance de calibration](calibration/PROVENANCE.json).

Reproduire la confirmation avec son empreinte complète et ces liaisons explicites de fixture et de plan :

```sh
obs="$study/confirmation/OBSERVATIONS.json"
obs_sha=$(sha256sum "$obs" | cut -d' ' -f1)
test "$obs_sha" = 07836b70b76e3012c8db4e5b2736bb3ac83ab22bc4a8ea1feca58e1b4309c02f || exit 1
python -I -B benchmarks/run_benchmark.py \
  --action-report "$obs" --action-report-sha256 "$obs_sha" \
  --action-fixture "$study/confirmation/FIXTURE.json" \
  --action-fixture-sha256 763af4de662fc6002ebf9bdbf901a7df623f3d0a97f23c01792e15d28f315ae8 \
  --action-plan "$study/confirmation/PLAN.json" \
  --action-plan-sha256 e08ab03cd7c9cbb6659a853c34301a03f351d7e0a12f18cf240826604ce1982f
```

Tests applicatifs et d’analyse hors ligne, avec fichiers locaux explicites ; aucun PYTHONPATH nécessaire sous `-I` :

```sh
ACTION_SOURCE="$PWD/benchmarks/action_transfer.py" \
ACTION_FIXTURE="$PWD/$study/FIXTURE.json" \
ACTION_BENCHMARK="$PWD/benchmarks/run_benchmark.py" \
python -I -B -m unittest discover -s "$study/tests" -p test_action_transfer.py

ACTION_ANALYSIS="$PWD/benchmarks/run_benchmark.py" \
ACTION_BENCHMARK="$PWD/benchmarks/run_benchmark.py" \
ACTION_FIXTURE="$PWD/$study/FIXTURE.json" ACTION_PLAN="$PWD/$study/PLAN.json" \
ACTION_VOLUME_ANALYSIS="$PWD/benchmarks/validation-20261022/CODE/volume_analysis.py" \
python -I -B -m unittest discover -s "$study/tests" -p test_action_analysis.py
```

Analyse appariée : bootstrap existant sur 12 groupes et quatre strates de famille, 10 000 tirages, graine 20261023. Usage connu pour 575/576 appels, mais seuls 527 sont chiffrables aux tarifs figés du 23 octobre 2026 : 48 usages comportent une écriture cache non tarifée ; un usage est manquant. Le sous-total connu de 0,6927518 USD n’est ni le coût complet ni la facture. Raisonnement compté une fois ; latence P2 seulement. Aucune frontière à dépense égale.

La correction du prompt conserve parseur, sécurité et oracles ; le correctif antérieur distingue demande et mémoire. Qualification hors ligne réussie. La calibration connue donne **47/48 résultats conformes** : 48 schémas acceptés, contrôles et appels uniques. Luna trie une fusion de catalogue anglaise par ordre croissant plutôt que décroissant dans catalog.json : échec métier réel. Ce sous-ensemble avec mémoire uniquement ne mesure aucun bénéfice indépendant ; comparaison directe impossible avec l’étude initiale.

L’échec au seuil initial de 48/48 reste consigné. Après revue sémantique indépendante, un [amendement prospectif explicite](https://github.com/Musyg/persistent-memory/blob/0eb33107ac5742ee3fcf6ab85da6acdf24cc799a/benchmarks/action-20261023/confirmation/PROTOCOL.md), figé avant toute réponse nouvelle, admet une unique étude de 576 appels. Le critère de poursuite est donc modifié ouvertement ; le seuil initial n’est pas déclaré réussi.

Les paramètres sont nouveaux, pour les mêmes 12 structures. Prompt et support qualifiés restent inchangés (SHA256 `74138918d82aa405261e60d1e7a258bbbc4e2dec6c629c7017ef8e381c35d9e4`), comme parseur, oracles, modèles, bras et analyse. Aucun réessai, ajustement du prompt ou nouvelle calibration. Toutes les réponses, erreurs et inconnues sont conservées pour publication. La calibration est exclue de l’estimation indépendante du bénéfice. L’étude nouvelle est clôturée ; ses résultats figurent plus haut. Les échecs initiaux restent inchangés.
