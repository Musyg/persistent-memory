# Fresh-parameter action study / Étude d’actions à paramètres nouveaux

## FR

Cet amendement est décidé **après** la calibration connue de 48 appels et **avant** toute réponse du nouvel échantillon. La calibration a donné 47/48 tâches conformes ; le seuil préalable de 48/48 est donc échoué et n’est pas réécrit. Les 48 propositions avaient un schéma accepté, un contrôle positif exact et un effet vérifié. Le seul échec métier est un tri croissant au lieu du tri décroissant demandé. Il reste un échec.

Le raccordement peut être mesuré malgré cette erreur du modèle. Cet amendement autorise une seule étude, sans nouvelle correction de prompt ni réessai : 24 paramétrisations nouvelles des mêmes 12 structures, deux langues, deux modèles, quatre bras et trois répétitions, soit 576 cellules. Toutes les réponses, erreurs et inconnues seront conservées et publiées, quel que soit le résultat. Ce n’est pas la poursuite automatique du protocole initial, ni 576 tâches indépendantes.

Le prompt qualifié est inchangé (`action_transfer.py`, SHA256 `74138918d82aa405261e60d1e7a258bbbc4e2dec6c629c7017ef8e381c35d9e4`). Parseur strict, oracles, limites de contexte, modèles, bras, contrôles et calcul statistique restent inchangés. Les nouveaux paramètres n’ont pas été consultés par l’auteur du prompt ou son relecteur. Aucun résultat de calibration n’entre dans l’estimation indépendante du gain.

Critère d’interface constaté : 48 propositions bornées acceptées, 48 contrôles exacts, 48 effets vérifiés, frontières P1/P2/P3 et autorité courante contrôlées, 48 émissions et réservations uniques. La justesse métier devient la variable mesurée, sans nouveau seuil gagnant. L’analyse appariée conserve les 12 groupes de structures et les quatre familles ; les répétitions ne deviennent pas de nouveaux groupes. Aucun avantage général ou à dépense égale n’est présumé.

## EN

This amendment was decided **after** the 48-call known-data calibration and **before** any response from the fresh sample. Calibration produced 47/48 correct tasks, so the original 48/48 gate failed and remains failed. All 48 proposals passed the schema, positive control and effect verification. The remaining task error sorted ascending rather than descending; it remains a failure.

One new study is admitted to measure actual performance despite that model error. There will be no further prompt changes or calibration retries: 24 fresh parameterizations of the same 12 templates, two languages, two models, four arms and three repetitions produce 576 cells. All responses, failures and unknowns will be retained and published regardless of outcome. This is an explicitly amended study, not automatic continuation under the original gate or 576 independent tasks.

The qualified prompt remains unchanged (support SHA256 above). Strict parsing, oracles, context bounds, models, arms, controls and statistical calculations remain unchanged. Neither the prompt author nor its reviewer inspected the new parameters. Calibration outcomes are excluded from independent benefit estimates.

Interface readiness rests on 48 bounded accepted proposals, 48 exact controls, 48 verified effects, checked P1/P2/P3 and current-authority boundaries, and 48 unique emissions and reservations. Business correctness is the measured outcome; no winning threshold is added. Paired analysis retains the 12 template clusters and four family strata. Repetitions do not create additional clusters. General superiority and equal-spending performance are not presumed.

## Frozen inputs / Entrées figées

| Input / Entrée | SHA256 |
| --- | --- |
| `FIXTURE.json` | `763af4de662fc6002ebf9bdbf901a7df623f3d0a97f23c01792e15d28f315ae8` |
| `PLAN.json` | `e08ab03cd7c9cbb6659a853c34301a03f351d7e0a12f18cf240826604ce1982f` |

Seed namespace / Namespace : `action-transfer-confirmation-20261023-v2`.
Maximum requests / Appels maximum : **576**, concurrency / simultanéité **3**, no retries / aucun réessai.
