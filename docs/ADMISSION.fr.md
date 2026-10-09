# Admettre une fiche revue ou une notice utile

[English](ADMISSION.md) · [Contrats structurés](STRUCTURED.fr.md) · [README](../README.fr.md)

`hermes_memory.admission` expose `admit(request, authority, sink, transform=None)` et `LabOrchestratorSink`. Cette frontière synchrone, facultative et limitée à la bibliothèque standard reçoit le **dossier de revue d'un hôte de confiance**, pas l'affirmation d'un modèle non fiable que ses propres preuves suffisent. Elle ne fournit ni extraction, fournisseur, RPC, base, service ni activation automatique en production.

```python
from hermes_memory.admission import admit, LabOrchestratorSink
from hermes_memory.admission_demo import example_request, demo_authority

sink = LabOrchestratorSink()
result = admit(example_request(), demo_authority, sink)
assert result['envelope']['decision'] == 'admitted'
assert result['handoff']['delivery'] == 'acknowledged'
```

`python -m hermes_memory.admission_demo` présente huit résultats synthétiques. Son autorité ne prend que des décisions locales d'exemple ; une intégration réelle nécessite l'autorité séparément authentifiée de votre hôte. Un ACK signifie uniquement que le callback a renvoyé l'accusé attendu.

## Entrée revue

Clés exactes : `schema, brief, accepts_format, workspace, limits, sources, dossier, c1_request` :

- Schéma `hermes.admission.request.v1`. `brief` est non vide, ≤8 192 caractères, ni analysé ni retourné. `accepts_format` est l'attestation booléenne de l'hôte qu'une fiche technique ou notice fixe convient à l'intention.
- `limits` contient les entiers `min_words, max_words` entre 1 et 10 000. Les limites s'appliquent aux fiches et aux notices.
- `sources` contient au plus 16 métadonnées `{id, workspace, version, sha256, state}`. Le texte brut n'apparaît que dans la requête structurée, lorsqu'elle est nécessaire.
- `dossier` contient `{reviewer, status, necessary_source_ids}`. Statut `supported`, `unknown`, `conflict` ou `not_reviewed` ; les statuts revus exigent un identifiant de relecteur. L'hôte doit inclure toutes les preuves nécessaires, y compris contraires. La bibliothèque ne peut pas prouver cette liste complète.
- `c1_request` est null hors statut supported. Sinon, elle suit le [contrat structuré](STRUCTURED.fr.md), avec mêmes espace/bornes/métadonnées, 1–4 faits requis sur un seul sujet ; toutes les sources rendues appartiennent à la liste nécessaire.

La requête est copiée après contrôle borné des types exacts : dictionnaires/listes/chaînes/entiers/booléens/null JSON, pas de tuples/sous-classes/flottants ; taille canonique ≤300 000 octets, profondeur ≤16, nœuds ≤16 384, éléments par collection ≤64. Les mutations des callbacks n'altèrent pas la capture. Une mutation concurrente durant la capture est hors contrat. Une entrée invalide n'appelle ni autorité ni consommateur.

## Autorité et remise unique

`authority(snapshot, stage)` reçoit uniquement `{workspace, sources:[{id, version, sha256}]}`, triées par identifiant nécessaire, aux étapes `before` et `before_handoff`. Aucun brief ou texte de preuve. Réponse exacte `{status, revision, disclose_withdrawal}` :

| Statut | Révision | Signification |
|---|---|---|
| allowed | identifiant | Poursuite seulement si les deux contrôles concordent. |
| revoked | identifiant | `withdrawn` si divulgation autorisée, sinon `access_unavailable`. |
| denied | identifiant | `access_unavailable`, quel que soit le drapeau de divulgation. |
| unavailable | null | `authority_unavailable`. |

`disclose_withdrawal` est booléen. Callback absent, réponse mal formée ou exception rendent l'autorité indisponible. Un changement de révision allowed produit `authority_changed` ; un retrait local ne peut pas être annulé par le callback.

Ces deux étapes concernent une requête qui atteint la préparation. Un premier refus d'autorité retourne immédiatement sa notice assainie. Pour une intention déclarée inadaptée par l'hôte, les données fournies ont déjà été parcourues et copiées pendant la capture d'entrée, y compris les corps de preuves éventuellement présents. Cette branche retourne seulement sa notice générique sans préparation/rendu C1 ni appel autorité/transform. La fonction ne récupère pas de preuves depuis un stockage externe. Une requête invalide n'appelle aucun callback.

Le `transform(body_bytes)` facultatif s'applique une fois au corps préparé non vide et doit rendre exactement les mêmes octets. Modification, exception ou sortie mal formée produisent `consumer_changed`. Le contrôle final d'autorité a toujours lieu et peut remplacer cette décision ; une notice de perte d'accès est reconstruite et n'est pas transformée à nouveau. La comparaison du tampon précède **l'unique appel** au consommateur, pas sa consommation.

`sink(envelope, receipt)` reçoit des copies distinctes seulement pour une fiche/notice admissible non vide. ACK exact attendu : `{status:'received', body_sha256:<SHA-256 du corps reçu>}`. La remise indique `attempted` (0/1), `delivery` (`not_attempted`, `acknowledged`, `unknown`) et un incident générique. Une exception après un effet conserve une tentative au résultat inconnu ; son texte n'est pas exporté et aucun nouvel essai n'est lancé. L'hôte décide d'une éventuelle reprise en tenant compte des effets du consommateur.

## Sortie et limites

Le retour contient `envelope`, `receipt`, `handoff`. L'enveloppe porte décision, type de corps (`technical_card`, `notice`, `none`), corps/nouvelle empreinte, identifiant opaque de requête, révision du contrat, révision d'autorité, état de revue, vérification du consommateur et `publication_atomic=False`. Le reçu ajoute cause, provenance admise et `extraction_measured=False`.

Les décisions distinguent `admitted`, `unknown`, `conflict`, `unsupported_intent`, `review_required`, `withdrawn`, `access_unavailable`, `authority_unavailable`, `authority_changed`, `consumer_changed`, `output_constraint` et `invalid_request`. Une preuve inconnue n'est pas une panne de transport ; un gabarit inadapté ne prouve pas qu'une autre approche ne peut satisfaire l'intention. Si la limite de mots est trop basse même pour une notice, le corps reste vide avec `output_constraint`.

Après perte d'accès, enveloppe et reçu exportés ne conservent ni anciens identifiants de source, provenance, empreinte de corps, ni état supported/conflict : revue `not_disclosed`, révision d'autorité null et provenance vide. Seule l'empreinte de la nouvelle notice permise reste. Un reçu privé admis contient volontairement l'extrait autorisé : protégez-le comme une preuve et ne le publiez pas par défaut.

La revue par l'hôte ne prouve ni implication sémantique ni exactitude d'extraction. Identité/authentification, disponibilité d'autorité, stockage, délais des callbacks, atomicité autorisation/publication, consommation et rappel de copies déjà remises ne sont pas fournis. Les bornes portent sur les données acceptées, pas sur la durée d'un callback arbitraire ou du Python hostile. Consulter les [limites de chargement/comptage](STRUCTURED.fr.md) et les tests synthétiques avant intégration.

La gestion des exceptions décrite ci-dessus couvre les sous-classes ordinaires d'`Exception`. Une interruption ou une autre `BaseException` peut se propager sans reçu retourné, y compris après un effet du consommateur. Aucun journal durable ni bac à sable pour les callbacks n'est fourni. L'hôte doit gérer séparément les interruptions et les effets incertains.
