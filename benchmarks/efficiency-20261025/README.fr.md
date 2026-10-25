# Coût d'un cycle mémoire après le chargement

25 octobre 2026 · [English](README.md) · [Mesures, calculs et empreintes](RESULT.json) · [Observations](observations.json) · [Protocole](PROTOCOL.json) · [Reproduire](REPRODUCE.fr.md)

Après le chargement de 1 000 sources, le cycle mémoire prend moins de temps avec le cœur `76dba2b1…` dans les trois comparaisons appariées. La réduction médiane observée est de **2,35 %**, soit **0,458 seconde**, avec une étendue de 1,67 à 2,69 %. Le chargement initial présente une réduction distincte de 29,13 % en médiane. Ces observations séparent le coût d'admission initial du coût d'un usage courant sur cette charge synthétique.

Les six cellules ont terminé en 402,323 secondes au total, sans erreur, timeout, remplacement ou nouvel essai de campagne. Chacune utilise un processus et une base neufs, dans l'ordre AB/BA/AB sur un hôte Linux. A désigne le cœur `35dd711a…`, B le cœur `76dba2b1…`; le banc et les données restent communs. Les plafonds actifs ont été observés : CPU 50 %, 1 Gio de RAM, aucun swap, 64 tâches au plus et aucun réseau. Le plafond est de 180 secondes par enfant et de 1 200 secondes pour l'unité. Les enfants ont été attendus, l'unité est inactive avec PID nul, le cgroup vide ou absent et la RAM temporaire supprimée.

## Cycle mesuré

Chaque processus charge d'abord 1 000 sources et synchronise l'index. Dans la même instance mémoire, il ajoute dix sources, lit leurs références et leurs contenus complets, synchronise l'index, puis effectue 50 recherches avec 50 lectures explicites. Les dix premières recherches portent chacune sur une nouvelle source; les 40 suivantes sont tirées dans le corpus initial avec la graine 20261021. Le cycle retire ensuite `note-1000`, contrôle le refus de lecture et l'index périmé, synchronise, vérifie l'absence de cette source et confirme que `note-1001` reste retrouvable et lisible.

| Paire | Ordre | Cycle A → B | Réduction | Ratio B/A | CPU du cycle A → B | Chargement initial A → B |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | AB | 19,497 → 18,973 s | 2,69 % | 0,9731 | 9,726 → 9,465 s | 55,133 → 39,096 s |
| 2 | BA | 19,496 → 19,038 s | 2,35 % | 0,9765 | 9,725 → 9,522 s | 55,280 → 39,172 s |
| 3 | AB | 19,300 → 18,977 s | 1,67 % | 0,9833 | 9,630 → 9,460 s | 55,167 → 39,094 s |

Le temps du cycle est le champ marginal du banc; il exclut l'ingestion et la première synchronisation. Le CPU est la somme des deltas utilisateur et système entre la première et la dernière frontière du cycle. Sa réduction médiane par paire est de **2,08 %**, avec une étendue de 1,76 à 2,68 %, soit une différence médiane de 0,203 seconde CPU. La différence médiane du chargement initial est de 16,073 secondes; sa réduction va de 29,09 à 29,14 %. Aucun de ces pourcentages n'est additionné aux résultats d'une étude antérieure.

## Phases et ressources

Les valeurs ci-dessous sont les médianes des trois observations de chaque bras, par phase. Elles ne forment pas une exécution recomposée. Le JSON conserve toutes les valeurs par cellule, les deltas CPU utilisateur et système, les I/O, les tailles par fichier et les échantillons RSS de chaque phase.

| Phase | Durée A → B | CPU utilisateur+système A → B |
| --- | ---: | ---: |
| Chargement : ingestion | 55,000 → 38,909 s | 27,437 → 19,417 s |
| Chargement : première synchronisation | 0,184 → 0,195 s | 0,094 → 0,098 s |
| Cycle : dix admissions | 1,094 → 0,774 s | 0,552 → 0,383 s |
| Cycle : lectures des admissions | 0,627 → 0,672 s | 0,331 → 0,331 s |
| Cycle : synchronisation | 0,189 → 0,195 s | 0,098 → 0,100 s |
| Cycle : 50 recherches et lectures | 16,406 → 16,271 s | 8,189 → 8,108 s |
| Cycle : retrait et contrôle de l'index périmé | 0,208 → 0,208 s | 0,118 → 0,118 s |
| Cycle : synchronisation après retrait | 0,188 → 0,198 s | 0,099 → 0,099 s |
| Cycle : contrôles finaux | 0,669 → 0,668 s | 0,328 → 0,327 s |

Les durées aux frontières et le chronomètre marginal du banc ont des périmètres légèrement différents. Le JSON garde les deux : l'écart va de 0,002 à 0,011 seconde. Ce n'est pas une mesure du surcoût total de la télémétrie. Chaque cellule écrit 44 états de progrès. Les contrôles, lectures et écritures de télémétrie contribuent au temps observé; aucun bras sans instrumentation n'en isole le coût.

Le stockage échantillonné passe de **2 166 923 octets après chargement** à **2 293 899 octets après le cycle**, soit 126 976 octets supplémentaires dans les six cellules. Les tailles par fichier restent disponibles; une égalité de tailles ne prouve pas l'identité binaire des bases. Les fichiers de données sont en RAM. Pour le cycle, `/proc/self/io` rapporte 0 octet lu au niveau stockage et 73 728 octets écrits, avec 177 945 418 caractères lus, 45 100 appels de lecture et 1 554 appels d'écriture. Les caractères écrits varient de 3 120 386 à 3 120 455. Ces compteurs décrivent le processus, dont les journaux de progrès; leurs unités ne sont pas interchangeables et ils ne prouvent pas une absence d'I/O matériel.

Le RSS courant final issu de `/proc/self/statm` va de 36 462 592 à 36 524 032 octets. Le pic déclaré par `getrusage`, conservé séparément, va de 35 680 256 à 36 290 560 octets. Les deux sources ne s'alignent pas sur ces observations; le JSON préserve leurs valeurs sans les remplacer ni en déduire un gain mémoire. Le pic déclaré concerne toute la vie du processus, y compris le chargement. Les pics entre deux instantanés de taille ou de RSS restent inconnus.

## Justesse, provenance et portée

Les six cellules passent les contrôles de contenu et de cycle, avec 50 éléments attendus, aucun résultat manquant ou inattendu, aucune troncature et 50 statuts completed. La séquence de requêtes, recalculée indépendamment depuis les sources synthétiques avant lancement, conserve l'empreinte `43246effb8574adaeb53eb0dff4984a1b2845f7bd2acbe8b1c204bb678c57bfe`. Chaque cycle comprend dix admissions, deux synchronisations, 53 recherches, 63 lectures et un retrait, soit 129 appels explicites après les 1 001 appels du chargement. Les 63 lectures incluent les deux refus de la source retirée et la lecture autorisée du témoin. Les recherches utilisent top_k 5 et un budget de 200 caractères.

Les sources effectivement importées et leurs constantes de liaison ont été observées pour chaque processus; les caches de bytecode sont absents. Les 36 fichiers de la collecte terminale correspondent aux contenus et empreintes de leurs reçus natifs. Les deux bras utilisent le même support hors ligne 0.3.0a2 avec trois modules épinglés par bras. La mesure porte sur ces codes et ce support, sans attribuer ces temps aux distributions a4 installées. L'échec initial de qualification, survenu avant ingestion, reste conservé séparément; la qualification corrigée passe avant cette campagne unique. Les empreintes du gel prospectif, du runner, des deux cœurs et des observations figurent dans le JSON.

Trois paires sont des observations descriptives. Les 50 recherches d'une cellule ne sont pas 50 réplications indépendantes; le cache froid et les effets de charge ou d'ordre ne sont pas contrôlés. Aucun seuil de gain n'était exigé et aucun test de significativité n'est produit. Cette mesure ne démontre ni supériorité générale, ni latence de production, qualité sémantique, réussite de mission d'agent ou durabilité après coupure électrique. Aucun appel fournisseur, téléchargement réseau ou changement de production n'a eu lieu. L'énergie, la facture et le coût complet restent inconnus.
