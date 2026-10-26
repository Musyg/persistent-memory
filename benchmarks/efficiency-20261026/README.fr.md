# Réduire le coût de validation des identifiants

26 octobre 2026 · [English](README.md) · [Mesures](measurements.json)

Une modification ciblée de la validation des identifiants réduit le temps instrumenté de **6,79 % en médiane** sur trois nouvelles comparaisons appariées. Le temps CPU baisse de **6,77 % en médiane**. Les six exécutions conservent les résultats attendus, y compris après le retrait d'une source.

Le changement remplace le parcours Python de chaque caractère par `re.search(r'[\x00-\x1f]', x)`, qui recherche les mêmes caractères de contrôle. Les règles restent identiques : chaîne de type exact, longueur UTF-8 de 1 à 512 octets et refus des caractères U+0000 à U+001F. DEL et les caractères de contrôle C1 restent acceptés comme auparavant. Un test de régression parcourt les 1 114 112 points de code Unicode, puis vérifie les chaînes mixtes, les frontières de longueur et les exceptions d'encodage. Il complète les tests fonctionnels existants, sans constituer autant de missions indépendantes.

| Paire | Ordre | Temps instrumenté A → B | Réduction | CPU A → B | Réduction CPU |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | AB | 116,384 → 107,498 s | 7,64 % | 58,048 → 53,641 s | 7,59 % |
| 2 | BA | 115,796 → 107,936 s | 6,79 % | 57,768 → 53,860 s | 6,77 % |
| 3 | BA | 115,686 → 108,497 s | 6,21 % | 57,720 → 54,124 s | 6,23 % |

A utilise le cœur `76dba2b1…`, B le cœur `80c55792…`. Chaque cellule emploie un processus et une base neufs, sur le même hôte Linux, avec le même banc et les mêmes données synthétiques. Elle charge 1 500 sources, en ajoute dix dans la même instance, effectue 50 recherches et contrôle les lectures, le retrait et la source témoin. Cela représente 63 lectures explicites et 53 recherches au total par cellule. Le stockage final observé est identique : 3 358 859 octets.

Les critères ont été fixés avant ces six exécutions : tous les contrôles doivent passer, la réduction médiane du temps instrumenté doit atteindre 3 %, le CPU doit baisser dans chaque paire et aucune paire ne doit présenter une régression de temps supérieure à 2 %. Un premier essai a servi à choisir ce seuil d'ingénierie ; ses mesures sont exclues du tableau et de la décision. Les six cellules ont terminé, sans remplacement ni nouvel essai.

Le temps instrumenté couvre le chargement et le cycle complet, avec revalidation et télémétrie. Le CPU est mesuré entre le début de l'ingestion et la fin des contrôles après retrait. Les phases incluses ne sont pas additionnées à leur total. Les plafonds observés sont de 50 % de CPU, 1 Gio de RAM, aucun swap, 64 tâches et un réseau privé. Le nettoyage des processus et de la RAM temporaire a été vérifié.

Cette mesure répond à une question précise : cette validation équivalente réduit-elle le travail du moteur sur la charge testée ? Les trois paires soutiennent cette décision d’ingénierie sur la charge testée. Le coût complet d'une mission, l'énergie et la latence d'un service en production relèvent de mesures distinctes. Les gains de cette étude ne s'ajoutent pas aux pourcentages des optimisations précédentes.

Les mesures proviennent d'une installation de la roue a4 avec les sources exactes de chaque bras appliquées dans un environnement isolé. Elles ne constituent pas la qualification d'une nouvelle archive distribuée. Le fichier de mesures conserve les empreintes du cœur, du banc, du calendrier de recherche et des critères utilisés.

Pour reproduire la charge, reprendre la [recette Linux existante](../efficiency-20261025/REPRODUCE.fr.md) pour créer un environnement neuf, sélectionner les modules et vérifier leurs imports sans bytecode. Adapter sa table de versions aux trios A et B de `reproduction.module_sha256` dans [les mesures](measurements.json) : A provient du commit `3c5251ef4b187410fe65b71a0e5b32184199d96a`, B du commit de publication contenant cette étude. Employer le même wheel du core a4 pour les deux bras et vérifier son empreinte indiquée dans les mesures. À l’étape d’installation de la recette, passer uniquement `$CORE_WHEEL` à pip ; cette étude utilise seulement le core. Le banc doit conserver l’empreinte `a2cfda65d6df85f76670af5efb413fc3f0d3d776cd8324e5251cf3b05bfa1b02`.

Dans cette recette, remplacer la commande de chaque cellule par :

```sh
TMPDIR="$CELL_RAM" timeout --signal=KILL 170s \
  "$ENV/bin/python" -I -B "$CHECKOUT/benchmarks/run_benchmark.py" \
  --documents 1500 --repetitions 50 --seed 20261021 \
  --volume-progress "$CELL_OUTPUT/progress.json" --volume-incremental-batch 10 \
  > "$CELL_OUTPUT/result.json" 2> "$CELL_OUTPUT/stderr.log"
```

Appliquer les trios dans l’ordre fixé **A, B, B, A, B, A**, avec un processus, une base et un répertoire RAM neufs par cellule. L’unité complète dispose de **1 050 s**, chaque enfant de **170 s**, avec **30 s de réserve** ; aucun départ après 870 s, ni si le temps restant ne couvre pas l’enfant et la réserve. Conserver les plafonds indiqués ci-dessus, les imports vérifiés et les reçus de nettoyage. Ne remplacer aucune cellule et ne pas relancer automatiquement. Les dix nouvelles sources sont recherchées une fois chacune, puis 40 recherches sont tirées sur les 1 500 sources initiales avec la graine 20261021 ; vérifier l’empreinte du calendrier dans les mesures. Recalculer les réductions par paire avec `1 - B/A`, puis leur médiane, après contrôle de tous les oracles. Le cache n’est pas contrôlé et les nouvelles durées dépendront de l’hôte et de sa charge.
