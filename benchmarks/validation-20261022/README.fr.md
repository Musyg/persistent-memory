# Mémoire persistante : confirmation indépendante

Cette étude mesure l’effet des informations conservées en mémoire sur les réponses d’un agent à 100 nouvelles tâches synthétiques, chacune dans un scénario distinct sans mémoire partagée avec les autres. Chaque tâche est exécutée trois fois. Les mêmes questions et réglages de modèle sont comparés avec mémoire, sans mémoire et, pour le modèle principal, avec une recherche lexicale.

Le [rapport complet](EXPECTED-REPORT/REPORT.fr.md) présente les réussites, échecs, résultats inconnus et intervalles de confiance. Son JSON et ses deux versions linguistiques peuvent être recalculés hors réseau à partir des réponses et jugements fournis.

| Modèle qui répond | Avec mémoire | Sans mémoire | Recherche lexicale |
|---|---:|---:|---:|
| GPT-6 Luna | 298/300 (99,33 %) | 29/300 (9,67 %) | 294/300 (98,00 %) |
| GPT-6.1 Sol | 300/300 (100 %) | 30/300 (10 %) | Non testée |

Le gain principal avec mémoire atteint 89,67 points de pourcentage, avec un intervalle nominal à 95 % de 89 à 90 points. La borne inférieure unilatérale à 95 % de la réussite absolue de Luna est de 98 % : les seuils de qualité gelés à 90 %/85 % sont satisfaits. Les 1 500 réponses ont été remises et les 3 000 jugements sont complets ; aucun résultat inconnu ni incident critique confirmé n’a été relevé. Les deux échecs de Luna avec mémoire restent dans les données : scénario `V22-F09-G10-T01`, répétitions 2 et 3. Ce contrôle de planning se suffit à lui-même, sans fait à récupérer : les deux réponses attribuent le mardi à la mauvaise personne.

L’intervalle mémoire/recherche lexicale va de −0,33 à +3,33 points : cette étude n’établit pas de supériorité sur la recherche lexicale. Le gain mémoire/sans mémoire du second modèle est de 90 points sur ce corpus. Ces comparaisons portent sur les scénarios décrits ci-dessous et ne certifient pas toutes les utilisations en production.

Les dix familles couvrent le rappel de faits, la composition entre sessions, les périodes de validité, les révisions, les procédures courtes, le retrait de sources, les homonymes, les faits indisponibles, les contrôles autonomes et l’isolation par espace de travail. Chaque famille comprend cinq tâches en français et cinq en anglais. Deux agents IA ont préparé les questions et oracles ; un relecteur IA distinct a contrôlé les 100 tâches et 190 documents avant leur gel local. Aucune réponse de modèle n’avait été observée au moment du gel.

L’évaluateur corrigé reçoit les preuves exactes transmises au modèle qui répond. Deux juges évaluent chaque réponse admissible sans voir le verdict de l’autre. Leur accord est nécessaire ; tout désaccord, verdict incomplet ou réponse indisponible reste inconnu. L’analyse principale compare, pour GPT-6 Luna, la réussite avec mémoire à celle sans mémoire. Sa qualité absolue est évaluée séparément : au moins 90 % de réussite conservatrice et une borne inférieure unilatérale nominale à 95 % d’au moins 85 %. Les intervalles d’effet sont nominaux à 95 % ; ils reposent sur 10 000 rééchantillonnages appariés des groupes de scénarios au sein de chaque famille, en gardant les trois répétitions ensemble. Les unités d’échantillonnage sont les 100 scénarios distincts. La comparaison mémoire/sans mémoire sur GPT-6.1 Sol et la comparaison mémoire/recherche lexicale sur Luna sont secondaires.

La [calibration de l’évaluateur sur huit cas](CALIBRATION/README.fr.md) constitue un contrôle diagnostique distinct. La [campagne précédente de 500 tâches](../validation-20261021/README.fr.md) reste archivée avec ses résultats initiaux et l’erratum d’évaluation.

## Recalcul local

Sous Linux, depuis ce dossier, avec Python 3.11 ou ultérieur :

```sh
sha256sum -c SHA256SUMS
python CODE/report.py --manifest REPORTING-INPUTS.json \
  --manifest-sha256 "$(cat REPORTING-INPUTS.sha256)" \
  --output /tmp/persistent-memory-confirmation-neuve
```

Le dossier de sortie doit être neuf. Cette commande n’appelle aucun modèle. Comparez le rapport produit à `EXPECTED-REPORT/`.

L’étude utilise le paquet mémoire public 0.3.0a2 via son consommateur de texte portable. Les scénarios sont courts et structurés ; le retrait porte sur les sources et le cloisonnement sur les espaces de travail. La reprise des dérivés, les droits par utilisateur et les historiques longs demandent des preuves spécifiques. Juges et relecteurs sont des agents IA ; aucun audit humain externe de qualité n’a été réalisé. Les erreurs des juges peuvent être corrélées ; les intervalles décrivent l’incertitude entre les scénarios échantillonnés, sans couvrir toutes les erreurs de jugement ni établir la représentativité en production. Le gel était local, avec publication après mesure. Toutes les données publiées sont synthétiques.
