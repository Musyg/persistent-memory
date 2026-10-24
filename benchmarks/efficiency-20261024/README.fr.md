# Coût d’admission à 1 000 sources

24 octobre 2026 · [English](README.md) · [Résultats](RESULT.json) · [Observations complètes](observations.json) · [Protocole](PROTOCOL.json)

Une correction ciblée du checkpoint réduit le travail d’ingestion dans trois comparaisons appariées sur un hôte Linux. Chaque exécution crée 1 000 sources synthétiques, synchronise l’index, effectue 50 recherches et 50 lectures explicites de validation, puis contrôle le retrait d’une source et la maintenance de l’index. Les six exécutions passent les mêmes contrôles de justesse.

Le checkpoint supplémentaire n’est désormais calculé que lorsqu’un `expected_epoch` est à contrôler. Les validations à l’entrée et à la sortie de transaction, l’intégrité du journal, les dépendances et les contrôles de version attendue restent en place. Aucun cache de validation n’est ajouté. Les [empreintes des sources](SOURCE-PINS.json) identifient le noyau précédent `35dd711a…`, le candidat `76dba2b1…`, leurs liaisons d’empreinte et la CLI inchangée.

## Résultats par paire

Chaque bras utilise un processus et une base neufs. A désigne le noyau précédent et B le candidat. Le CPU correspond au temps utilisateur et système écoulé entre la première frontière d’ingestion et la dernière frontière de validation.

| Paire | Ordre | Durée instrumentée A → B | Ingestion A → B | CPU A → B |
| --- | --- | ---: | ---: | ---: |
| 1 | AB | 72,107 → 56,379 s | 55,046 → 39,298 s | 35,989 → 28,131 s |
| 2 | BA | 71,771 → 55,629 s | 54,540 → 38,878 s | 35,807 → 27,777 s |
| 3 | AB | 72,482 → 56,293 s | 55,110 → 39,077 s | 36,163 → 28,089 s |

Les réductions médianes par paire sont de **22,33 % pour la durée totale** (étendue de 21,81 à 22,49 %), **28,72 % pour l’ingestion** (28,61 à 29,09 %) et **22,33 % pour le CPU** (21,84 à 22,42 %). La durée instrumentée comprend les validations et la télémétrie du banc. Les trois paires progressent sur les deux critères de performance fixés avant lancement : durée totale et ingestion. Aucun timeout ni remplacement n’a été nécessaire ; le job complet a pris 388,624 secondes.

Chaque exécution retrouve les 50 éléments attendus, sans omission, résultat inattendu ou candidat tronqué. La séquence de requêtes est identique. Le retrait provoque toujours `index_stale` avant synchronisation, puis un résultat vide avec statut completed. Les six stockages finaux occupent 2 220 171 octets ; cette égalité de taille ne signifie pas que les bases sont identiques octet par octet. Le RSS courant reste proche de 35 Mo à la dernière frontière.

## Environnement et provenance

Les deux bras utilisent le même environnement de laboratoire et un stockage en RAM. Les wheels observés sont `hermes_memory_core-0.3.0a2` et `hermes_policy_registry-0.2.0a2` ; trois fichiers de modules épinglés sont sélectionnés explicitement pour chaque bras. La mesure compare donc **le code 35dd au code 76db dans un support commun 0.3.0a2**. Elle ne mesure pas les distributions a4 installées. Les [paquets a4 qualifiés séparément](qualification.json) passent leurs tests depuis les wheels et les sources reconstruites dans deux environnements Linux.

Les [observations brutes](observations.json), inchangées, conservent les étiquettes du brouillon préparatoire. La [projection d’admission](ADMISSION.json) décrit l’autorisation séparée, délivrée avant l’intent exclusif de lancement. Elle retire le chemin du reçu privé et conserve les empreintes originales. Aucun résultat n’a été réétiqueté ou rejoué pour corriger ce détail de présentation.

## Rejouer la charge

Utiliser Linux, Python avec SQLite FTS5 et le [banc existant](../run_benchmark.py), SHA `ab92430cd614e9297d0eb18797d30bd0da012a6315705eea58620f4e911caf33`. Le [protocole](PROTOCOL.json) donne les six appels, la graine, l’empreinte des requêtes, l’oracle et les limites de ressources. `--repetitions 50` désigne 50 recherches dans une exécution, pas 50 répétitions indépendantes du benchmark complet.

Pour une nouvelle comparaison, installer le wheel a4 courant dans deux environnements virtuels neufs. Dans A, remplacer uniquement `core.py`, `typed_memory.py` et `typed_protocol.py` par leurs versions du commit public `1554beda0ef3e57621eca8974c197514302f369e`. B conserve les sources courantes. Vérifier les deux ensembles avec [SOURCE-PINS.json](SOURCE-PINS.json), puis utiliser exactement le même fichier de benchmark. Cette préparation fournit un nouvel environnement commun ; elle ne reconstruit pas les octets des wheels du laboratoire archivé.

Pour chaque cellule, créer un répertoire privé neuf sous `/dev/shm`, le désigner par `TMPDIR` et utiliser le Python du bras choisi :

```sh
TMPDIR=/dev/shm/votre-cellule-privee-neuve \
  /chemin/vers/le-venv-choisi/bin/python -I -B benchmarks/run_benchmark.py \
  --documents 1000 --repetitions 50 --seed 20261021 \
  --volume-progress /chemin/vers/un-progres-neuf.json > resultat-neuf.json
```

Exécuter les cellules à la suite, dans l’ordre AB/BA/AB. L’enveloppe archivée impose une unité de 1 200 secondes au maximum, un quota CPU de 50 %, 1 Gio de RAM, aucun swap, 64 tâches au plus et aucun réseau, avec 180 secondes par enfant. Après dépassement, arrêter le processus enfant, attendre sa fin, puis supprimer son répertoire RAM. Conserver les timeouts et les cellules non démarrées, sans remplacement. Comparer les trois paires après réussite du même oracle de justesse. La CLI fournie exécute la charge ; l’opérateur de déploiement n’est pas nécessaire pour utiliser la bibliothèque.

Trois paires restent des observations descriptives, sans distribution robuste ni test de significativité. Le cache froid n’est pas contrôlé. Aucun résultat à 5 000 sources, gain de classement sémantique, latence de production, coût d’infrastructure ou économie d’énergie n’est établi. L’[étude antérieure de sérialisation](../efficiency-20261023/core-optimization-20261023/README.fr.md) utilisait un autre support, non contrôlé ; ses pourcentages ne sont pas combinés avec ceux-ci.
