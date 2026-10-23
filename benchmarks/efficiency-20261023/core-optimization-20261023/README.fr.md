# Allocations du cœur mémoire et reprise après interruption

23 octobre 2026 · [English](README.md) · [Mesures et empreintes des reçus](RESULT.json) · [Étude antérieure du coût de génération](../README.fr.md)

Une correction limitée de l'[autorité mémoire](../../../src/hermes_memory/core.py) réduit le temps observé sur une même charge synthétique, exécutée sur deux hôtes Linux. Elle évite des sérialisations de références redondantes, le double décodage JSON d'une même entrée du journal et la revalidation d'une référence déjà validée. Les contrôles du journal, de l'état matérialisé et de l'ancre conservée restent exécutés à chaque transaction. Aucun cache de validation n'est ajouté. Les sous-classes de références conservent leur comportement de sérialisation antérieur.

## Charge mesurée

Le [banc de volume existant](../../run_benchmark.py) a été exécuté avant et après la correction, à 100 et 1 000 sources synthétiques. Chaque exécution couvre l'ingestion, la synchronisation de l'index, 50 recherches chronométrées, 50 lectures explicites de validation, le retrait d'une source et la maintenance de l'index. Les séquences de requêtes sont identiques. Tous les contrôles de résultats attendus passent, sans omission ni élément inattendu.

À 1 000 sources :

| Hôte Linux | Charge instrumentée avant | Après | Réduction observée | Ingestion avant → après |
| --- | ---: | ---: | ---: | ---: |
| A | 100,985 s | 72,699 s | 28,01 % | 76,892 → 55,498 s |
| B | 94,704 s | 68,490 s | 27,68 % | 72,248 → 52,365 s |

Ces durées couvrent la charge instrumentée, dont les validations et la télémétrie. Il n'y a qu'une observation par hôte, taille et version ; l'état du cache, vide ou déjà alimenté, n'a pas été contrôlé. Les écarts décrivent ces exécutions et ne démontrent pas une supériorité générale de vitesse. Le profilage a identifié les allocations à corriger ; ses temps sont exclus de cette comparaison.

Après synchronisation et retrait, les tailles des fichiers restent identiques : 364 682 octets à 100 sources et 2 220 171 octets à 1 000. Il s'agit d'une comparaison des tailles, pas d'une identité des bases octet par octet. Le JSON conserve les temps CPU, le RSS courant et maximal du processus, les durées par phase et les nombres d'appels. À 1 000 sources, le RSS courant en fin d'exécution passe d'environ 38,0 à 38,7 Mo sur A et de 36,9 à 38,5 Mo sur B. L'énergie, le prix de l'infrastructure et le coût complet restent inconnus.

Le cas à 5 000 sources n'a pas été exécuté : sa prévision prospective dépassait le plafond de 600 secondes. Aucune latence mesurée, aucun score de réussite ni conclusion de passage à l'échelle ne lui est attribué ici.

## Reprise après arrêt réel d'un processus

Le cœur corrigé passe également quatre trajectoires SIGKILL fixes sur chaque hôte. Chaque trajectoire rouvre la mémoire dans un nouveau processus, refuse la source A retirée et retourne la source B indépendante, par les lectures directes et typées.

| Interruption | Hôte A : arrêt jusqu'à B vérifié | Hôte B |
| --- | ---: | ---: |
| Recherche interrompue pendant un retrait | 0,348 s | 0,299 s |
| Synchronisation, écriture retardée/CAS et restauration d'une ancienne copie du contenu et de l'index | 0,227 s | 0,267 s |
| Autorité validée avant publication de l'ancre | 0,350 s | 0,307 s |
| Projection de l'outbox terminée avant acquittement | 0,383 s | 0,320 s |

Le délai commence à l'envoi de SIGKILL et inclut la synchronisation explicite ou la réparation auditée de l'ancre, puis les vérifications HTTP dans un nouveau processus. L'écart avec l'ancre provoque d'abord un refus de service jusqu'à la réparation explicite ; le rejeu de l'outbox reste idempotent. Le banc attend la fin de tous les processus qu'il a lancés et récupère leurs statuts de sortie. Ces huit trajectoires sont des observations de laboratoire finies, pas des percentiles de reprise, un SLO de disponibilité ni un test de coupure électrique.

## Portée et reproduction

Aucun appel fournisseur ni aucune action sur un service de production n'intervient. Cette note résume des reçus natifs archivés ; leurs empreintes et celles du cœur avant/après figurent dans `RESULT.json`. Elle ne remplace ni ne modifie l'étude antérieure de génération par modèle.

Avec les deux paquets installés, exécuter le mode de volume existant depuis la racine du dépôt, sous Linux :

```sh
python -I -B benchmarks/run_benchmark.py --documents 1000 --repetitions 50 --seed 20261021 --volume-progress volume-progress.json > volume-result.json
```

Les nouvelles durées dépendent de l'hôte et de sa charge. Les résultats de reprise archivés ont aussi nécessité des pauses contrôlées, de vrais SIGKILL, de nouveaux processus et un audit explicite de l'ancre en laboratoire. Une exécution ordinaire du banc de volume ne reproduit pas ces séquences d'interruption.
