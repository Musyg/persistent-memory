# Mémoire persistante — résultats de validation

100 tâches choisies, 100 groupes de scénarios, trois répétitions et 1 500 épisodes prévus. Les tâches d’un même groupe ne sont pas indépendantes.

| Indicateur | Résultat |
|---|---|
| Réponses remises | 1500 / 1500 |
| Épisodes non exécutés | 0 |
| Exécution complète confirmée | oui |
| Incidents critiques confirmés | 0 |
| Réussite A, bornes conservatrices | 99.33 % / 99.33 % |
| Effet A−B, intervalle d’incertitude nominal 95 % | 89.00 % / 90.00 % |
| Qualité absolue conforme | oui |
| Bénéfice différentiel confirmé | oui |
| Exécution, sécurité et non-remise conformes | oui |

Le calcul conserve les inconnus et tous les épisodes prévus. Le bootstrap apparié rééchantillonne les groupes dans chaque famille (10 000 tirages); il ne transforme pas les répétitions en tâches indépendantes.

## Comparaisons secondaires

- gpt-6-luna, memory_on − simple_baseline: 100 tâches du sous-ensemble gelé; 95 %: -0.33 % / 3.33 %; seed 20261025.
- gpt-6.1-sol, memory_on − memory_off: 100 tâches du sous-ensemble gelé; 95 %: 90.00 % / 90.00 %; seed 20261026.

## Stabilité et première répétition

`pass^3` exige trois réussites confirmées; un inconnu reste visible. Les comptes ci-dessous portent sur des tâches.

| Modèle / bras | 3/3 | Échec | Inconnu |
|---|---:|---:|---:|
| gpt-6-luna/memory_off | 9 | 91 | 0 |
| gpt-6-luna/memory_on | 99 | 1 | 0 |
| gpt-6-luna/simple_baseline | 96 | 4 | 0 |
| gpt-6.1-sol/memory_off | 10 | 90 | 0 |
| gpt-6.1-sol/memory_on | 100 | 0 | 0 |

Première répétition A/B : gain=90, loss=0, tie_success=10, tie_failure=0, unknown=0.

## Émissions et non-remise

| Phase | Émissions confirmées | Émission incertaine | Non-émis confirmés | Jamais exécutés |
|---|---:|---:|---:|---:|
| generation | 1500 | 0 | 0 | 0 |
| judges | 3000 | 0 | 0 | 0 |

Une émission incertaine conserve ce statut et son exposition financière; elle ne compte pas comme zéro émission. Les épisodes jamais exécutés sont un sous-ensemble, pas une colonne à additionner.

| Modèle / bras | Tâches / groupes | Non-remise | Borne supérieure unilatérale95 % |
|---|---:|---:|---:|
| gpt-6-luna / memory_off | 100 / 100 | 0.000 % | 0.000 % |
| gpt-6-luna / memory_on | 100 / 100 | 0.000 % | 0.000 % |
| gpt-6-luna / simple_baseline | 100 / 100 | 0.000 % | 0.000 % |
| gpt-6.1-sol / memory_off | 100 / 100 | 0.000 % | 0.000 % |
| gpt-6.1-sol / memory_on | 100 / 100 | 0.000 % | 0.000 % |

Bornes obtenues par le bootstrap groupé gelé, 10000tirages et seed20261024, en conservant les trois répétitions. Les Wilson descriptifs de première répétition restent disponibles séparément dans le JSON.

## Familles — lecture exploratoire

| Famille | Tâches | Bornes de l’effet |
|---|---:|---|
| F01 | 10 | 100.00 % / 100.00 % |
| F02 | 10 | 100.00 % / 100.00 % |
| F03 | 10 | 100.00 % / 100.00 % |
| F04 | 10 | 100.00 % / 100.00 % |
| F05 | 10 | 100.00 % / 100.00 % |
| F06 | 10 | 100.00 % / 100.00 % |
| F07 | 10 | 100.00 % / 100.00 % |
| F08 | 10 | 100.00 % / 100.00 % |
| F09 | 10 | -3.33 % / -3.33 % |
| F10 | 10 | 100.00 % / 100.00 % |

## Latences observées

| Modèle / bras | N | p50 (s) | p95 (s) |
|---|---:|---:|---:|
| gpt-6-luna / memory_off | 300 | 1.301 | 1.963 |
| gpt-6-luna / memory_on | 300 | 1.449 | 2.514 |
| gpt-6-luna / simple_baseline | 300 | 1.470 | 2.460 |
| gpt-6.1-sol / memory_off | 300 | 2.312 | 3.339 |
| gpt-6.1-sol / memory_on | 300 | 2.517 | 3.690 |

Temps total du consommateur pour les réponses complètes disposant d’une trace; préparation, récupération et contrôles compris. Les données absentes ne sont pas remplacées par zéro.

## Coûts et portée

Plafond de génération : 27.74016 USD; plafond des juges : 41.9328 USD.
Débit conservateur rapproché : 212.0767488 USD; coût calculé depuis l’usage : inconnu; facture : inconnue.

Deux juges IA, aucun audit humain; leurs erreurs peuvent être corrélées. Le test technique à 5 000 sources a atteint sa borne de 40 minutes : cette charge n’est pas qualifiée. Les résultats concernent le composant public et le consommateur portable exercés, sans certification de toute la production Hermes.

Identifiants, états de chaque épisode, sources et SHA256 figurent dans REPORT.json et MANIFEST.json.
