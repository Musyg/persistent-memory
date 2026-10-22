# Mémoire persistante — résultats de validation

500 tâches choisies, 100 groupes de scénarios, trois répétitions et 3 900 épisodes prévus. Les tâches d’un même groupe ne sont pas indépendantes.

| Indicateur | Résultat |
|---|---|
| Réponses remises | 3900 / 3900 |
| Épisodes non exécutés | 0 |
| Exécution complète confirmée | oui |
| Incidents critiques confirmés | 0 |
| Réussite A, bornes conservatrices | 86.00 % / 94.93 % |
| Effet A−B, intervalle d’incertitude nominal 95 % | 61.00 % / 77.33 % |
| Qualité absolue conforme | non |
| Bénéfice différentiel confirmé | oui |
| Exécution, sécurité et non-remise conformes | oui |

Le calcul conserve les inconnus et tous les épisodes prévus. Le bootstrap apparié rééchantillonne les groupes dans chaque famille (10 000 tirages); il ne transforme pas les répétitions en tâches indépendantes.

## Comparaisons secondaires

- gpt-6-luna, memory_on − simple_baseline: 100 tâches du sous-ensemble gelé; 95 %: -2.67 % / 26.67 %; seed 20261025.
- gpt-6.1-sol, memory_on − memory_off: 100 tâches du sous-ensemble gelé; 95 %: 56.67 % / 77.33 %; seed 20261026.

## Stabilité et première répétition

`pass^3` exige trois réussites confirmées; un inconnu reste visible. Les comptes ci-dessous portent sur des tâches.

| Modèle / bras | 3/3 | Échec | Inconnu |
|---|---:|---:|---:|
| gpt-6-luna/memory_off | 87 | 398 | 15 |
| gpt-6-luna/memory_on | 383 | 42 | 75 |
| gpt-6-luna/simple_baseline | 64 | 22 | 14 |
| gpt-6.1-sol/memory_off | 20 | 76 | 4 |
| gpt-6.1-sol/memory_on | 81 | 9 | 10 |

Première répétition A/B : gain=327, loss=0, tie_success=91, tie_failure=21, unknown=61.

## Émissions et non-remise

| Phase | Émissions confirmées | Émission incertaine | Non-émis confirmés | Jamais exécutés |
|---|---:|---:|---:|---:|
| generation | 3900 | 0 | 0 | 0 |
| judges | 7800 | 0 | 0 | 0 |

Une émission incertaine conserve ce statut et son exposition financière; elle ne compte pas comme zéro émission. Les épisodes jamais exécutés sont un sous-ensemble, pas une colonne à additionner.

| Modèle / bras | Tâches / groupes | Non-remise | Borne supérieure unilatérale95 % |
|---|---:|---:|---:|
| gpt-6-luna / memory_off | 500 / 100 | 0.000 % | 0.000 % |
| gpt-6-luna / memory_on | 500 / 100 | 0.000 % | 0.000 % |
| gpt-6-luna / simple_baseline | 100 / 100 | 0.000 % | 0.000 % |
| gpt-6.1-sol / memory_off | 100 / 100 | 0.000 % | 0.000 % |
| gpt-6.1-sol / memory_on | 100 / 100 | 0.000 % | 0.000 % |

Bornes obtenues par le bootstrap groupé gelé, 10000tirages et seed20261024, en conservant les trois répétitions. Les Wilson descriptifs de première répétition restent disponibles séparément dans le JSON.

## Familles — lecture exploratoire

| Famille | Tâches | Bornes de l’effet |
|---|---:|---|
| F01 | 50 | 92.00 % / 96.00 % |
| F02 | 50 | 68.00 % / 87.33 % |
| F03 | 50 | 88.67 % / 96.67 % |
| F04 | 50 | 94.00 % / 99.33 % |
| F05 | 50 | 75.33 % / 87.33 % |
| F06 | 50 | 73.33 % / 87.33 % |
| F07 | 50 | 82.00 % / 93.33 % |
| F08 | 50 | 12.00 % / 36.00 % |
| F09 | 50 | -7.33 % / 6.67 % |
| F10 | 50 | 59.33 % / 64.67 % |

## Latences observées

| Modèle / bras | N | p50 (s) | p95 (s) |
|---|---:|---:|---:|
| gpt-6-luna / memory_off | 1500 | 1.356 | 2.163 |
| gpt-6-luna / memory_on | 1500 | 1.554 | 3.019 |
| gpt-6-luna / simple_baseline | 300 | 1.551 | 2.533 |
| gpt-6.1-sol / memory_off | 300 | 2.591 | 4.183 |
| gpt-6.1-sol / memory_on | 300 | 2.842 | 5.750 |

Temps total du consommateur pour les réponses complètes disposant d’une trace; préparation, récupération et contrôles compris. Les données absentes ne sont pas remplacées par zéro.

## Coûts et portée

Plafond de génération : 32.90112 USD; plafond des juges : 109.02528 USD.
Débit conservateur rapproché : 141.9995136 USD; coût calculé depuis l’usage : inconnu; facture : inconnue.

Deux juges IA, aucun audit humain; leurs erreurs peuvent être corrélées. Le test technique à 5 000 sources a atteint sa borne de 40 minutes : cette charge n’est pas qualifiée. Les résultats concernent le composant public et le consommateur portable exercés, sans certification de toute la production Hermes.

Identifiants, états de chaque épisode, sources et SHA256 figurent dans REPORT.json et MANIFEST.json.
