# Preuves techniques historiques

Ces fichiers projettent les reçus techniques du 21 octobre 2026 pour leur publication. Les valeurs mesurées, identifiants de tests, cas synthétiques, compteurs, fautes et rejets attendus sont conservés. Les chemins absolus, identités de machines, journaux et enveloppes de transport sont exclus. Les environnements sont désignés A et B; les fichiers d'origine restent privés et inchangés.

| Vérification historique | Résultat conservé |
|---|---|
| Distributions installées, A et B | Par environnement : 147 tests core wheel + 147 sdist + 49 policy wheel + 49 sdist = 392 exécutions, zéro échec/erreur/skip. Les imports depuis site-packages sont attestés séparément, sans inventer un chemin d'installation public. |
| Trajectoires techniques, A et B | Les mêmes 3 000 cas, six familles de 500, reproduits sur les deux environnements : 86 965 appels explicites, 57 763 invariants de lecture, 1 000 fautes attendues interceptées et 1 000 rejets attendus par environnement. Ce sont 3 000 trajectoires uniques, pas 6 000 clients ou tâches indépendants. |
| Charge 100, A et B | 100 recherches sur chaque environnement. B ne reproduit que cette échelle; aucune mesure à 1 000 ou 5 000 n'est attribuée à B. |
| Charge 1 000, A | 1 000 recherches; p50 0,3781398144783452 s, p95 0,38777976483106613 s. Ingestion76,00318102305755 s; ces durées restent distinctes de la recherche. |
| Charge 5 000, A | Timeout effectif à 40 minutes, sans arrêt demandé par l'utilisateur. Aucun rapport final; phase et nombre partiel d'opérations inconnus. Cette échelle n'est pas qualifiée. Le timeout ne prouve pas une panne sémantique. |

Les deux rapports de trajectoires et les deux rapports de charge A sont conservés en octets exacts depuis les contenus embarqués dans les reçus; leurs hashes de fichiers terminaux sont vérifiés. Les résumés projetés gardent aussi les durées des workers, distinctes des durées internes du benchmark. La charge B conserve le cas et son rapport complet. Les distributions gardent tous les `test_ids`, les erreurs, les compteurs et la parité des sources de test.

Les répétitions wheel/sdist ne constituent pas 784 garanties indépendantes.

`BENCHMARK-SOURCE-PINS.json` distingue les versions réellement exercées : charge SHA256 `66ebda8d8f297c25c63c5fcc9f2839089d95d33921a1137af9fbabb26e4b8766`, trajectoires SHA256 `641c1a20f879cf914babbed9b0be6119aa90f4d528791b17401e574a40059991`. Ces preuves historiques ne sont pas réétiquetées comme qualification d'un futur commit ou de nouvelles distributions.

Les latences de charge portent sur `typed.search`, sans les vérifications explicites `memory.read`. Le cache froid n'était pas contrôlé. Le pic RSS est le maximum du processus sur sa durée de vie, pas une consommation mémoire incrémentale. Les requêtes utilisent des jetons lexicaux synthétiques; elles n'évaluent pas la qualité du classement ou des tâches métier autonomes. Aucun appel fournisseur n'a été effectué par ces benchmarks. Ces échelles sont distinctes des 500 tâches de l'évaluation de réponses.

`PROVENANCE.json` donne les SHA des reçus privés, des chemins logiques, les champs retirés et les digests communs des valeurs conservées. `INSTALLED-ORIGIN-ATTESTATIONS.json` décrit la projection de l'origine installée. `VERIFICATION.json` décrit uniquement le contrôle documentaire de cette extraction, sans nouveau benchmark. `MANIFEST.json` et `SHA256SUMS` lient les octets publics. La projection est postérieure à la mesure; elle n'est ni une prérégistration externe ni une certification de toute la production Hermes. Root doit encore qualifier l'arbre public final avant promotion.
