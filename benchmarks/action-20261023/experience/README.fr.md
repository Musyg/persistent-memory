# Transformer un résultat observé en leçon réutilisable

23 octobre 2026 · [English](README.md) · [Résultats](RESULT.json) · [Observations compressées](OBSERVATIONS.json.gz) · [Plan des épisodes](PLAN.json)

Dans cette étude synthétique, un modèle exécute une tâche A, reçoit un retour sur son résultat réel, en extrait une leçon puis tente une tâche B différente. La leçon dérivée augmente le nombre de réussites observées par rapport à l'absence d'expérience pour les deux modèles. Face à la trace complète de A et à son feedback, elle apporte neuf réussites supplémentaires à Luna et fait égalité pour Sol.

## Résultats B vérifiés

Chaque ligne porte sur 24 missions B. Les 192 résultats B sont connus ; réussir exige le fichier métier attendu et un contrôle de fin valide, vérifiés par un processus distinct qui rouvre les fichiers produits. Les tokens d'entrée couvrent le prompt B complet ; le contexte mémoire n'a pas été tokenisé séparément.

| Modèle | Bras d'expérience | Missions B réussies | Tokens d'entrée B |
| --- | --- | ---: | ---: |
| GPT-6 Luna | Leçon dérivée | 22/24 | 22 718 |
| GPT-6 Luna | Trace complète + feedback | 13/24 | 57 194 |
| GPT-6 Luna | Sans expérience | 7/24 | 16 532 |
| GPT-6 Luna | Leçon retirée | 7/24 | 16 565 |
| GPT-6.1 Sol | Leçon dérivée | 24/24 | 23 310 |
| GPT-6.1 Sol | Trace complète + feedback | 24/24 | 57 324 |
| GPT-6.1 Sol | Sans expérience | 12/24 | 16 536 |
| GPT-6.1 Sol | Leçon retirée | 10/24 | 16 557 |

Pour Luna, la leçon dérivée apporte 15 réussites de plus que l'absence d'expérience et neuf de plus que la trace brute. Pour Sol, elle apporte 12 réussites de plus que l'absence d'expérience et rejoint la trace brute. Ces écarts appariés décrivent cette suite. Ils n'établissent ni avantage universel, ni significativité statistique, ni supériorité à dépense égale.

## Ce qui est appris, puis transféré

Les six familles portent sur les identifiants, les bornes de seuil, les signes débit/crédit, les conflits de révision, l'encodage CSV et les indicateurs d'approbation. Chacune comprend une instance française et une anglaise. Le fichier réellement produit en A et son feedback révèlent une convention du destinataire ; B change l'objectif et les données tout en conservant cette convention. Par exemple, le traitement d'une valeur exactement au seuil dans A peut éclairer la sélection de lignes d'un autre rapport en B.

A réussit dans 24 épisodes sur 48. Les 48 retours sont discriminants, y compris après un résultat A incorrect. L'extraction utilise seulement la trace réelle de A et ce feedback, avant l'exécution de B. L'extracteur produit 48 candidats bien formés et choisit la bonne convention structurée dans les 48 cas. L'explication en texte libre n'a pas reçu d'annotation sémantique ; ce score ne valide pas chaque phrase des leçons.

Chaque candidat est enregistré par `Memory.derive`, avec des dépendances vers la trace réelle de A et son feedback, sans promotion en politique active. Le bras brut reçoit exactement l'entrée complète de l'extracteur, dont le prompt, la réponse, les effets observés de A et le feedback. Aucun résumé ne s'y substitue. Les quatre bras B disposent des mêmes droits métier et des mêmes données. Le bras de retrait révoque un parent de l'expérience enregistrée pour vérifier son exclusion de la réutilisation ; il reste autorisé à exécuter B sans cette expérience. Ce retrait est un contrôle de sécurité, hors des deux comparaisons principales.

L'étude comporte **48 épisodes appariés** : six familles × deux langues × deux modèles × deux répétitions. Chaque épisode contient un appel A, une extraction et quatre appels B, soit **288 appels modèles réels**. Les répétitions et les bras partagent le contexte d'un même épisode. Ils ne représentent pas 288 tâches métier indépendantes. L'ordre des bras B est fixé à brut → dérivé → absence → retrait, avec trois épisodes exécutés concurremment ; les durées ne constituent pas une comparaison de latences indépendantes. Aucun appel n'a été retenté, aucun cas remplacé ni aucun résultat écarté après observation. Aucun intervalle de confiance, p-value ou bootstrap n'est présenté.

## La mauvaise convention est-elle répétée ?

Le Registry existant relit les 192 effets B dans 16 partitions et conserve **119 réussites, 73 échecs et aucun résultat de qualité inconnu**. Les 7 424 fichiers de l'étude d'origine restent inchangés. La [projection du Registry](REGISTRY.json) conserve les comptes de vérification et leur provenance.

La récidive répond à une question plus précise : après une mauvaise convention en A, le fichier réel de B reproduit-il cette convention ? Le dénominateur est de **24 épisodes éligibles par bras**, dont 11 pour Luna et 13 pour Sol. Les résultats de qualité complets ci-dessus portent toujours sur les 48 missions B de chaque bras, tous modèles confondus.

| Bras d'expérience | Épisodes éligibles | Erreur de convention répétée | Convention correcte en B | Cause inconnue |
| --- | ---: | ---: | ---: | ---: |
| Leçon dérivée | 24 | 0 | 24 | 0 |
| Trace complète + feedback | 24 | 2 | 18 | 4 |
| Sans expérience | 24 | 17 | 5 | 2 |
| Leçon retirée | 24 | 13 | 6 | 5 |

Si le fichier B ne correspond à aucune des deux conventions légales, sa cause reste inconnue. Un échec générique n'est pas automatiquement une récidive ; une convention correcte ne suffit pas non plus à satisfaire toutes les exigences de fichier et de contrôle. Ce diagnostic reste donc distinct de la réussite complète de B.

## Contexte et coûts

Le parcours d'expérience autorise 8 000 caractères et cinq éléments, sous le plafond inchangé de 10 240 octets pour la requête complète. La [décision prospective sur le plafond](CAP-DECISION.md) et la [représentation sans perte du prompt](PROMPT-REPRESENTATION.md) sont fixées après qualification factice et avant les appels modèles. Les études antérieures gardent leurs prompts et limites. Un plafond commun n'implique pas une consommation réelle de tokens ou un coût identiques.

Sol obtient la même qualité qu'avec la trace brute en consommant moins de tokens d'entrée B avec la leçon dérivée. La construction de cette leçon exige aussi un appel d'extraction. Un usage reposant sur la trace brute seule pourrait s'en passer : les seuls appels B ne démontrent donc pas une économie totale de tokens. Le travail de construction reste compté séparément :

| Phase, deux modèles réunis | Appels | Tokens d'entrée | Tokens de sortie |
| --- | ---: | ---: | ---: |
| A et son résultat observé | 48 | 28 327 | 3 525 |
| Extraction de la leçon | 48 | 88 609 | 8 797 |
| Les quatre bras B | 192 | 226 736 | 24 012 |

L'usage déclaré totalise 380 006 tokens pour les 288 appels. L'estimation historique de génération est de **0,2639163 USD pour 187 appels seulement**. Les 101 autres comportent des écritures de cache que ce calculateur figé ne chiffre pas ; le compteur déclaré est de 208 158 tokens de cache-write. Leur coût reste inconnu. L'extraction n'a notamment aucune couverture tarifaire ici et ne doit pas être considérée comme gratuite. La facture, le coût complet de construction et de fonctionnement de la mémoire, ainsi qu'une comparaison à dépense égale restent indisponibles.

## Reproduction

Le [protocole](PROTOCOL.md), le plan et les observations conservent l'étude réelle figée. Avec les deux paquets installés, le calcul hors ligne utilise `gzip`, fourni par la bibliothèque standard, pour lire `OBSERVATIONS.json.gz`, puis transmet les observations décodées et les octets exacts de `PLAN.json` à `calculate_experience` dans le [module de benchmark existant](../../run_benchmark.py). Il n'ajoute aucun appel fournisseur. Les scores détaillés et la couverture du calcul restent dans `RESULT.json`.
