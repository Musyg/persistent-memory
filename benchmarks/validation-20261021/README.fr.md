# Mémoire persistante : données de validation reproductibles

Ce dossier archive la campagne close les 21–22 octobre 2026. La qualité absolue **n’est pas qualifiée** : le taux de réussite conservateur atteint **86,00 %**, avec une borne inférieure unilatérale à 95 % de **83,67 %**, sous les exigences de 90 % / 85 %. Les juges initiaux recevaient les identifiants des preuves, mais pas leurs textes ; ils ont ainsi pénalisé des détails pourtant étayés. Ces résultats automatiques historiques dépendent de cet évaluateur et ne constituent pas une mesure calibrée de la qualité métier. Lire le [bilan et l’erratum sur l’évaluation](ASSESSMENT.fr.md) avec les chiffres inchangés de `EXPECTED-REPORT/REPORT.fr.md` et `REPORT.en.md`.

Le plan comprend 500 tâches synthétiques choisies, 100 groupes de scénarios, trois répétitions et 3 900 épisodes de génération. La comparaison principale oppose le composant public de mémoire typée à l’absence de mémoire sur les 500 tâches. Le sous-ensemble gelé de 100 tâches ajoute le comparateur lexical existant et une confirmation sur un second modèle de génération. Deux juges IA évaluent les réponses admissibles ; leurs erreurs peuvent être corrélées. L’étude ne constitue ni un audit humain indépendant de la qualité, ni une garantie pour tous les usages en production.

Le protocole et les oracles ont été gelés localement avant les appels. Les empreintes et reçus documentent cette chaîne interne ; la publication GitHub intervient après la mesure et ne constitue pas une prérégistration externe horodatée. Chaque cas, politique et répétition utilise une mémoire fraîche, avec une requête fournie par la fixture. Les 500 tâches évaluent ce parcours de récupération et réponse ; elles n’évaluent ni un planner autonome ni une mémoire unique accumulant 500 sessions.

## Recalculer hors réseau

Utiliser Linux et Python 3.12, version qualifiée. Le rapport ne dépend que de la bibliothèque standard Python : aucun compte, clé API, modèle payant, service privé Hermes, base de données ou accès réseau n’est nécessaire au recalcul.

Depuis ce dossier :

```sh
sha256sum -c SHA256SUMS
python3 -P -B CODE/report.py \
  --manifest REPORTING-INPUTS.json \
  --manifest-sha256 "$(cat REPORTING-INPUTS.sha256)" \
  --output ../rapport-memoire-recalcule
diff -u EXPECTED-REPORT/REPORT.fr.md ../rapport-memoire-recalcule/REPORT.fr.md
diff -u EXPECTED-REPORT/REPORT.en.md ../rapport-memoire-recalcule/REPORT.en.md
diff -u EXPECTED-REPORT/REPORT.json ../rapport-memoire-recalcule/REPORT.json
```

Chaque calcul écrit dans un nouveau dossier. `CODE/report.py` et `CODE/volume_analysis.py` sont des copies exactes des implémentations qualifiées. Tous les épisodes prévus et les inconnus sont conservés, avec le bootstrap apparié par groupes de scénarios, les graines gelées, `pass^3`, les comparaisons secondaires, les bornes de non-remise et les critères de preuve séparés. Un essai absent ou incertain ne devient pas implicitement une réussite, un échec, une absence d’envoi ou une dépense nulle. Un coût calculé depuis l’usage reste distinct d’une facture réelle.

Les critères annoncés sont explicites : exécution confirmée, aucune violation critique confirmée observée, non-remise opérationnelle d’au plus 1 %, réussite principale d’au moins 90 % avec une borne inférieure unilatérale à 95 % d’au moins 85 %, et borne inférieure à 95 % de l’effet apparié positive pour annoncer un bénéfice. Ce sont les exigences d’ingénierie de cette étude, pas une norme de certification universelle. Les répétitions ne sont pas comptées comme des tâches indépendantes.

## Ce qui est conservé

`DATA/CASES.json`, `ORACLE.json`, `METADATA.json` et `SUBSET.json` conservent leurs octets synthétiques d’origine. Les empreintes des cas et de l’oracle correspondent aux engagements initiaux. Les réponses générées, preuves, réponses des juges, statuts, inconnus, identités de modèles, usages et durées mesurées restent présents dans les fichiers normalisés. Aucune réponse en échec n’est réécrite pour obtenir une réussite.

Le plan et le gel d’étude publics portent explicitement la mention de **projections d’analyse créées après mesure**, avec les SHA256 des sources d’origine. Ils conservent les mêmes identifiants d’épisodes, modèles, bras et répétitions, en retirant les hôtes, chemins et autorisations d’exploitation. Ce ne sont pas des autorisations exécutables et ils ne prétendent pas recréer le gel historique. `PROVENANCE.json` détaille les empreintes sources, métadonnées retirées et liens de hashes rebondés ; il atteste l’égalité du rapport laboratoire/public complet hors provenance de chemins et d’empreintes, ainsi que l’égalité exacte des deux rapports rédigés.

Il s’agit du **recalcul exact des preuves enregistrées**. Demander de nouvelles réponses aux modèles est une autre opération : elle implique un fournisseur, ses coûts, des sorties potentiellement différentes et l’enregistrement des versions demandées/retournées et des limites. Cette archive ne promet ni des poids de modèles immuables, ni des réponses futures identiques, ni la validation de toute l’agence Hermes.

## Composant public et reproduction technique

Le composant public s’installe depuis le dépôt `Musyg/persistent-memory` avec son paquet Python existant :

```sh
# Depuis la racine du dépôt téléchargé, séparément du recalcul hors réseau.
python3 -m pip install .
```

Le candidat qualifié ajoute `--trajectories` au fichier existant `benchmarks/run_benchmark.py` ; son SHA256 est `641c1a20f879cf914babbed9b0be6119aa90f4d528791b17401e574a40059991`. Utiliser une révision du dépôt contenant exactement ce fichier ; une version antérieure peut ne pas encore proposer cette option.

Exemples depuis cette version qualifiée du dépôt :

```sh
python3 benchmarks/run_benchmark.py --trajectories 3000 --seed 20261021
python3 benchmarks/run_benchmark.py --documents 100 --repetitions 100 --seed 20261021
python3 benchmarks/run_benchmark.py --documents 1000 --repetitions 1000 --seed 20261021
```

Ces contrôles locaux ne sollicitent aucun modèle. Leurs preuves techniques précisent les graines réellement employées et les bornes de ressources. L’essai à 5 000 sources a atteint sa limite de 40 minutes et reste non qualifié ; ces commandes ne relancent pas cette charge implicitement et ne transforment pas son dépassement en réussite. Les trajectoires techniques restent distinctes des 500 tâches métier et de l’évaluation des réponses des modèles.
