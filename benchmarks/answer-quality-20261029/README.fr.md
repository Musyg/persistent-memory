# Mémoire persistante : comparaison sur huit historiques

Sur huit historiques synthétiques de développement, la mémoire obtient **77 réussites sur 96**, contre **29 sur 96** pour la référence lexicale avec versions et contrôles de validité. L'évaluation porte sur le cœur portable de Persistent Memory. Quatre historiques français et quatre anglais constituent une même famille de scénarios. La réplication indépendante reste à réaliser.

| Résultat primaire | Avec mémoire | Référence lexicale |
| --- | ---: | ---: |
| Réussite | 77 | 29 |
| Échec | 10 | 58 |
| Inconnu | 9 | 9 |

Les 96 comparaisons appariées donnent 45 gains, aucune perte observée, 26 réussites communes, 10 échecs communs et 15 paires inconnues. Chaque tentative reste au dénominateur. Deux lecteurs Codex ont évalué les réponses à l'aveugle : ils ont produit 382 jugements sur les 191 artefacts disponibles, avec des décisions de réussite concordantes. La génération utilise un seul modèle, gpt-6-luna.

La collecte compte 192 appels HTTP réels, sans nouvelle tentative, et 191 artefacts relus. Dix-sept identifiants de contrôle incorrects et une réponse JSON invalide ne reçoivent aucun crédit de réussite primaire. L'analyse complémentaire du contenu, réalisée a posteriori, donne séparément 85/96 et 31/96 ; l'artefact absent reste inconnu.

La mémoire fournit tous les faits requis pour 79 des 88 questions comportant de tels faits, contre 22/88 pour la référence, soit 111/120 faits contre 39/120. Les versions fournies sont valides. Cette meilleure couverture décrit un mécanisme plausible du résultat, sans établir la cause de chaque réponse. Un rejeu isolé des neuf omissions d'horaire reproduit les paquets : les faits éligibles occupent les rangs 10 à 52, après la limite de cinq éléments retenus.

L'usage donne une estimation de génération de **0,038438475 USD**, avec le palier `default` et 228 347 jetons d'écriture de cache. Par réussite primaire : 0,000250514 USD avec mémoire, 0,000660308 USD pour la référence. La facture et le coût complet de l'agence restent inconnus.

[EVIDENCE192.json](EVIDENCE192.json) contient les faits, contrôles, textes originaux et verdicts des 192 cas. Avec Python 3, `python verify_pilot.py` recalcule les résultats et l'estimation tarifaire, en vérifiant leurs empreintes. Les tarifs datés et leurs sources officielles figurent dans [RESULTS.json](RESULTS.json).
