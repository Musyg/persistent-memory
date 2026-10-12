# Démonstration LanceDB synthétique optionnelle

[English](BENCHMARK-LANCE.md)

Cet exemple relie une recherche hybride locale aux contrôles de version et de retrait de Persistent Memory. Il utilise quatre sources fictives et des vecteurs tridimensionnels prédéfinis. Il a été exécuté sous Linux avec **LanceDB 0.25.3 et PyArrow 23.0.1**.

## Exécuter l'exemple

Utilisez un environnement Linux dans lequel Persistent Memory est installé, depuis la racine du dépôt. L'[exemple d'installation](../README.fr.md#essayer-un-parcours-complet) décrit l'installation du noyau.

Le benchmark existant reste le mode par défaut et ne nécessite pas LanceDB :

```sh
.venv/bin/python benchmarks/run_benchmark.py
```

Pour la démonstration optionnelle, installez explicitement ses dépendances dans cet environnement :

```sh
.venv/bin/python -m pip install 'lancedb==0.25.3' 'pyarrow==23.0.1'
.venv/bin/python benchmarks/run_benchmark.py --lance-hybrid
```

Ces bibliothèques sont facultatives et importées uniquement par ce mode. Une fois les dépendances installées, la démonstration ne demande ni API fournisseur, ni modèle, ni téléchargement. Elle transmet explicitement le vecteur et le texte, sans fonction d'embedding ni fallback dense. Les erreurs remontent.

## Ce qui est vérifié

L'exemple crée une table Lance locale temporaire et un index FTS natif. Les lignes candidates portent des refs versionnées. Avant de construire le contexte, `Memory.validate` vérifie chaque ref auprès de l'autorité courante et fournit le texte autorisé de l'enveloppe ; le texte de la projection ne fait pas autorité.

Une version est ensuite remplacée et une autre source retirée. `TypedMemory` refuse son index obsolète jusqu'à une synchronisation explicite. L'exemple ajoute la ligne de remplacement à Lance et **reconstruit explicitement l'index FTS synthétique**. Deux lignes obsolètes restent présentes afin de vérifier leur exclusion par revalidation. Ce rafraîchissement appartient à l'exemple ; il ne constitue pas une synchronisation automatique de production.

Le checkpoint d'autorité est vérifié avant la recherche puis avant de rendre le contexte, limité à 200 caractères. La requête échoue si le checkpoint de projection est obsolète ou si l'autorité change pendant la recherche.

| Observation | Résultat attendu |
|---|---|
| Sources et candidats admissibles au départ | 4 |
| Lignes de projection après remplacement | 5 |
| Candidats courants admissibles ensuite | 3 |
| Lignes obsolètes exclues | `source_revoked`, `version_not_current` |
| Dimensions des vecteurs | 3 |

## Lire la sortie

Le JSON indique les versions des bibliothèques, les candidats et éléments admissibles, les motifs d'exclusion, le contexte et le temps de requête. Les identifiants et durées varient ; les invariants contrôlés sont reproductibles. Les invocations par défaut et optionnelle ont toutes deux réussi avec les versions testées.

Les vecteurs sont de petites valeurs prédéfinies. La note sans pertinence particulière reste admissible. Cet exemple vérifie le binding explicite du SDK et la revalidation par l'autorité sur des données fictives ; il ne mesure ni qualité de classement, ni mémoire apprise, ni débit, ni comportement à cache froid, ni supériorité générale de vitesse.
