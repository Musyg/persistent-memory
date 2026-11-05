# Transfert d’expérience avec Hermès et ECC

[English](README.md)

**Campagne terminée le 5 novembre 2026.** Les 32 cas ont été exécutés dans quatre conditions, avec le même modèle et jusqu’à trois tentatives pour la nouvelle mission. Hermès réussit 10 des 16 missions où une règle apprise reste valable, contre 7 pour l’adaptation locale d’ECC. Quand la nouvelle mission impose une autre règle, les résultats sont de 11 et 14 sur 16.

**Cette campagne ne confirme pas l’avantage attendu selon les critères fixés avant les essais.** Elle rend vérifiables les réussites, les échecs, les corrections et le parcours des enseignements, sans retirer les cas défavorables.

## Résultats

Chaque colonne porte sur les mêmes cas dans les quatre conditions.

| Condition | Règle précédente valable, résultat final /16 | Nouvelle règle, résultat final /16 | Premier fichier correct /32 | Fichier final correct /32 |
| --- | ---: | ---: | ---: | ---: |
| H · Mémoire Hermès | 10 | 11 | 6 | 21 |
| E · Adaptation ECC | 7 | 14 | 5 | 21 |
| T · Historique des missions | 9 | 14 | 4 | 23 |
| N · Sans historique | 6 | 12 | 5 | 18 |

Le premier fichier et le fichier final sont évalués selon la règle métier complète. Les valeurs finales montrent ce que l’agent accomplit avec son budget de correction. La différence entre premier et dernier fichier décrit ce parcours ; elle n’isole pas à elle seule l’effet causal de la boucle.

Dans les cas de transfert, l’écart Hermès–ECC est de **+18,75 points de pourcentage**. Les trois réussites supplémentaires concernent la famille « stock » : 7/8 contre 4/8. La famille « admission » est à égalité, 3/8 dans les deux conditions.

Le signal attendu exigeait un gain observé d’au moins 20 points et un résultat statistiquement favorable dans les deux familles. Une analyse séparée vérifie la marge de non-dégradation quand la règle change. Aucun de ces deux critères de conclusion n’est rempli. Le test directionnel conjoint donne p = 1 ; l’intervalle simultané à 95 % de l’effet va de −44,4 à +64,6 points. ECC réussit trois missions avec une nouvelle règle sur lesquelles Hermès échoue. La marge de 5 points de non-dégradation n’est pas établie. [Résultat recalculable](RESULT.json)

## D’une mission à l’autre

Pour chaque cas, l’agent exécute six missions A dont les résultats sont vérifiés. Il reçoit ensuite une mission B avec de nouvelles données et doit produire un CSV. Les 16 cas de transfert conservent la convention de seuil des missions précédentes. Dans les 16 autres, la nouvelle mission définit explicitement la convention à appliquer. Chaque groupe comprend huit cas d’admission et huit cas de gestion de stock.

| Condition | Contexte ajouté à la nouvelle mission |
| --- | --- |
| H | Les enseignements qu’Hermès extrait, valide et retrouve. |
| E | Les enseignements qu’ECC appelle « instincts », s’il en retient pour la nouvelle session. |
| T | Le déroulé des six missions précédentes et leurs résultats vérifiés. |
| N | Aucun historique des missions précédentes. |

Le même Qwen3-Coder-30B-A3B-Instruct quantifié et le même agent de développement sont utilisés dans les quatre conditions. Dans la boucle native, l’agent planifie, produit un fichier et le soumet au contrôle. Il peut ensuite analyser le retour et corriger le fichier, dans la limite de trois tentatives. Il ne s’agit donc pas d’une évaluation limitée à une seule réponse.

Le contrôle accessible à l’agent vérifie le format et les lignes dont le traitement est commun aux deux conventions de seuil. Le juge indépendant vérifie la règle complète, y compris l’égalité au seuil. Ses réponses attendues ne sont pas remises à l’agent. Le résultat terminal est la mesure principale. [Méthode et paramètres](METHOD.fr.md)

La comparaison porte sur l’intégration native d’Hermès et une adaptation locale d’ECC. Ce dépôt public fournit le noyau de mémoire réutilisable et les éléments publics de vérification.

## Enseignements transmis et couverture des preuves

Le parcours complet d’extraction et de consommation est attesté dans 19 cas Hermès sur 32. Dans les 13 autres, le normaliseur conserve un état d’extraction indéterminé : 12 sources A ne fournissent pas un résultat littéral exploitable sans exécuter le code généré, et une leçon proposée contredit la convention démontrée par sa source. Les validations refusent ces entrées. Ce statut n’efface ni les artefacts B ni leurs notes : les 128 résultats métier restent évalués. Il ne permet pas, à lui seul, de conclure à une panne du stockage.

Pour ECC, le parcours est attesté sur les 32 cas : deux transmettent un contexte d’instincts non vide, les 30 autres une sélection vide connue. Une abstention valide compte comme un parcours observé, sans être présentée comme un transfert d’expérience réussi. L’historique T est disponible dans les 32 cas.

Ces distinctions séparent la qualité du livrable de la preuve que le système a extrait et transmis un enseignement. [Données par condition](ARMS.json) · [Format des données](FORMAT.fr.md)

## Ressources

La campagne comprend 544 phases et **1 016 générations locales**, avec **1 002 470 tokens d’entrée et 125 865 tokens de sortie** comptabilisés. Les 3 916 opérations HTTP instrumentées concernent la préparation des requêtes et les contrôles du serveur. Elles ne constituent pas un compte des outils métier utilisés par l’agent.

Aucun appel à une API de génération payante n’a été effectué. Le matériel et l’énergie ne sont pas chiffrés. Les missions A, communes aux quatre conditions, sont comptées une seule fois dans le total de campagne. Le calcul par condition distingue cette préparation commune des coûts propres d’apprentissage et de résolution. [Détail des ressources](RESULT.json) · [Convention de comptage](FORMAT.fr.md)

Le tableau suivant additionne l’apprentissage propre à chaque condition et ses missions B. Les six missions A de chaque cas constituent une préparation commune : 384 générations, 155 049 tokens d’entrée et 37 063 de sortie pour l’ensemble des cas.

| Condition | Générations | Tokens d’entrée | Tokens de sortie | Durée cumulée des appels modèle |
| --- | ---: | ---: | ---: | ---: |
| H | 234 | 221 411 | 38 444 | 179,0 s |
| E | 146 | 278 289 | 15 291 | 93,2 s |
| T | 131 | 273 344 | 19 539 | 115,9 s |
| N | 121 | 74 377 | 15 528 | 72,0 s |

Les durées additionnent les appels observés. Elles ne mesurent ni le temps GPU seul ni la durée totale du banc, qui comprend démarrages, contrôles, attentes de port et archivage. Hermès consomme moins de tokens d’entrée qu’ECC dans ce montage, mais davantage de générations, de tokens de sortie et de temps d’appel. Ces mesures ne démontrent donc pas un avantage d’efficacité global.

## Vérifier les résultats

Les fichiers publics contiennent des cas synthétiques et les sorties autorisées après revue. Les données de mémoire privées, identifiants d’exploitation, secrets, journaux de production et sauvegardes privées ne font pas partie de cette publication.

Depuis ce dossier, avec Python 3.11 ou ultérieur :

```sh
python -I -B verify.py
python -I -B REGRADING/verify_regrading.py
```

La première commande recalcule les agrégats et les critères statistiques à partir des 32 cas et 128 lignes publiés. La seconde réévalue les artefacts synthétiques disponibles avec l’oracle typé, sans exécuter le code produit par le modèle. [Annexe de vérification](REGRADING/README.fr.md)

Les critères, le corpus et les paramètres ont été fixés avant la confirmation. Les anciens essais de développement et le témoin ci-dessous sont exclus de ses scores. Les incidents de collecte ont été réconciliés sans rejouer les phases de génération. Le résultat fonctionnel historique de [12/12](../../MEMORY-COMPARISON.md) reste attaché à son évaluation initiale.

## Témoin préalable, hors score

Sur un cas synthétique déjà utilisé, le parcours corrigé a employé 39 générations. Hermès a stocké quatre enseignements validés et son lecteur en a transmis trois au planificateur et au Coder. L’observateur ECC a analysé les 24 événements des missions A en 0,806 s et retourné une liste vide valide.

| Condition | Premier contrôle accessible à l’agent | Verdict métier final | Tentatives Coder |
| --- | --- | --- | ---: |
| H | Échec | Réussite | 2 |
| E | Échec | Échec | 3 |
| T | Échec | Réussite | 2 |
| N | Échec | Échec | 3 |

Ce contrôle de qualification vérifie le fonctionnement de la boucle et le passage effectif des enseignements. Il ne contribue pas au résultat confirmatoire. Son premier contrôle de format est distinct de la note métier complète du premier fichier présentée plus haut. [Données du témoin](witness-summary.json)

## Provenance ECC

Le bras E utilise **ECC Continuous Learning v2.1**, issu du projet d’Affaan Mustafa et de ses contributeurs, au commit `b38be6a7f6350964d59328b52f0624e1d1d552d1`. Le manifeste amont indique `ecc-universal` 2.2.3, sous licence MIT. Le banc exécute les hooks d’observation et de démarrage de session épinglés ; il adapte l’analyse de l’observateur à un appel JSON avec Qwen3-Coder en local. Les résultats portent sur cette adaptation, ces deux familles de tâches et ce budget.

[Sources épinglées](https://github.com/affaan-m/ECC/tree/b38be6a7f6350964d59328b52f0624e1d1d552d1) · [Documentation du skill](https://github.com/affaan-m/ECC/blob/b38be6a7f6350964d59328b52f0624e1d1d552d1/skills/continuous-learning-v2/SKILL.md) · [Licence MIT](https://github.com/affaan-m/ECC/blob/b38be6a7f6350964d59328b52f0624e1d1d552d1/LICENSE)
