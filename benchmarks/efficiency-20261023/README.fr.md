# Qualité, tokens et coût de génération observés

[English](README.md) · [Résultat complet](RESULT.json) · [Entrées épinglées](INPUTS.json) · [Preuves de reproduction](REPRODUCTION.json)

Cette **analyse secondaire exploratoire** reprend les 1 500 réponses déjà publiées dans l’[étude de confirmation Fresh100](../validation-20261022/README.fr.md). Elle n’ajoute aucun appel modèle, aucun jugement et aucune modification des scores historiques. L’usage en tokens est complet pour les 1 500 réponses. Chaque réponse est reliée à son résultat de qualité figé par modèle, cas, configuration et répétition.

## Empreinte observée

Chaque ligne porte sur 300 réponses : 100 groupes de scénarios synthétiques, répétés trois fois.

| Configuration | Réponses correctes / 300 | Tokens d’entrée + sortie | Génération estimée en USD | p95 du consommateur |
| --- | ---: | ---: | ---: | ---: |
| Luna, sans mémoire | 29 | 57 000 | 0,0099552 | 1,963 s |
| Luna, avec mémoire | 298 | 118 188 | 0,0188084 | 2,514 s |
| Luna, recherche lexicale | 294 | 124 017 | 0,0195409 | 2,460 s |
| Sol, sans mémoire | 30 | 61 124 | 0,240344 | 3,339 s |
| Sol, avec mémoire | 300 | 122 053 | 0,415418 | 3,690 s |

Sur ces réponses, Luna avec mémoire consomme **4,70 % de tokens en moins** et coûte **3,75 % de moins en génération estimée** que la recherche lexicale. L’entrée comporte 5,14 % de tokens en moins. Le p95 observé est toutefois environ 2,16 % plus élevé. Ces temps couvrent préparation, récupération, génération et contrôles ; ils n’isolent pas la latence du fournisseur et ne constituent pas un benchmark de vitesse contrôlé.

La qualité atteint 298 réponses correctes sur 300, contre 294. L’intervalle d’effet apparié à 95 % de l’étude initiale reste **−0,33 à +3,33 points de pourcentage** : ni supériorité ni non-infériorité de qualité ne sont établies. Aucun nouvel intervalle d’incertitude n’a été calculé pour les différences de tokens ou de coût. Ces écarts ne démontrent pas une dominance générale ni une frontière à dépense effective en tokens identique.

Face au contrôle sans mémoire, les deux modèles obtiennent les gains de qualité déjà publiés, mais consomment **davantage** de tokens et d’argent. La mémoire ne réduit donc pas les tokens par rapport à ce contrôle. Le coût par réponse conforme de cette cohorte reste une observation : ce n’est pas le prix garanti d’une future tâche quelconque, et il n’inclut ni reprises ni travail humain.

## Périmètre du calcul

- Les tarifs sont ceux **figés le 22 octobre 2026**, pour le texte en traitement standard : Luna 0,10/0,50 USD par million de tokens d’entrée/sortie ; Sol 2/10 USD. Ce sont les hypothèses historiques du calcul, pas une promesse de tarif actuel. Leurs sources figurent dans `INPUTS.json`.
- L’estimation de génération s’élève à **0,7040665 USD pour les 1 500 réponses historiques**. Ce n’est ni un nouveau coût de cette analyse ni une facture. Appels des juges, récupération, stockage, ingestion, infrastructure et travail humain sont exclus. La facture réelle reste inconnue.
- Cache, écriture de cache, audio et prédiction sont nuls. Les 42 tokens de raisonnement déclarés sont déjà compris dans les tokens de sortie ; ils ne sont pas facturés une seconde fois par le calcul. Une catégorie non nulle sans tarif pris en charge provoque un rejet explicite.
- Le contexte mémoire totalise 43 182 caractères Python et 44 391 octets UTF-8 par modèle ; le contexte lexical, 47 835 caractères et 49 227 octets. Les tokens du contexte n’ont pas été mesurés séparément. Un écart en caractères ou octets n’est pas une mesure de tokenisation.
- Les trois comparaisons entre configurations d’un même modèle comptent chacune 300 réponses appariées, avec trois répétitions dans les mêmes 100 groupes. Les 900 paires ne deviennent pas 900 tâches indépendantes. Aucun nouveau juge, intervalle bootstrap, seuil gagnant ou choix de tâches n’est ajouté.
- Les différences entre modèles restent descriptives. Leurs prompts complets contiennent des identifiants de références générés séparément ; tous leurs octets ne sont donc pas maintenus identiques. Il n’y a ici ni historique complet, ni long contexte, ni comparaison en production ou à dépense réalisée identique.

## Reproduire sous Linux

Depuis ce dépôt ou sa distribution source extraite, avec le paquet installé dans un environnement neuf :

```sh
python -I -B -m unittest discover -s tests -p test_product.py -v
python -I -B benchmarks/run_benchmark.py --efficiency > efficiency.json
cmp efficiency.json benchmarks/efficiency-20261023/RESULT.json
```

Deux environnements Linux produisent exactement les mêmes octets et passent chacun 15 tests ciblés du produit. L’empreinte du manifeste par défaut est imposée. Un manifeste personnalisé nécessite `--efficiency-inputs PATH` et `--efficiency-inputs-sha256 HASH` ; ses références doivent rester dans l’arborescence des benchmarks. Un usage absent ou inconnu, une identité mal reliée, un total incohérent, un poste tarifaire non pris en charge ou un prix invalide provoque un échec explicite.

Les données sources et rapports initiaux restent inchangés. Les [preuves antérieures du cycle de vie](https://github.com/Musyg/persistent-memory/tree/6c18450579fce9c071808c431cdbcb345771bced/benchmarks/lifecycle-20261022) conservent leurs empreintes de source dans le commit `6c18450` ; l’ajout de modes CLI ne modifie pas rétrospectivement cette étude. Le prochain point distinct est l’usage de la mémoire dans un processus neuf pour produire un artefact réellement vérifié. Cette analyse d’empreinte ne répond pas à cette question.
