# Faits structurés et contrat mécanique de sortie

[English](STRUCTURED.md) · [Admission](ADMISSION.fr.md) · [README](../README.fr.md)

Ces API synchrones, facultatives et limitées à la bibliothèque standard rendent des **faits structurés déjà revus** dans des gabarits français finis. Elles n'extraient pas les faits, n'établissent pas leur vérité et ne déduisent pas qu'une source implique une affirmation. Les imports partagent un même graphe d'implémentation vérifié ; `import hermes_memory` reste inchangé.

```python
from hermes_memory.structured_memory import render, canonical
from hermes_memory.quality_contract import OutputContract, validate_output
from hermes_memory.admission_demo import example_request

request = example_request()['c1_request']  # entrée synthétique déjà revue
def authority(snapshot, stage):
    return {'status': 'allowed', 'revision': 'demo-v1'}
result = render(request, authority)
assert result['status'] == 'ok'
report = validate_output(result['body'], OutputContract(1, 120, 'fr', ('demo-note',)))
assert report['mechanical_pass']
assert report['semantic_status'] == 'not_evaluated'
```

## Entrée et rendu

`render(request, authority)` reçoit un dictionnaire exact : `schema='hermes.structured.request.v1'`, `workspace`, `sources`, `facts`, `plan`, `contract`. `admission_demo.example_request()` fournit un exemple complet et modifiable. Le domaine est volontairement restreint :

| Champ | Contrat |
|---|---|
| sources | Au plus 16 dictionnaires : `id, workspace, version, sha256, text, state`. Texte UTF-8 ≤16 384 octets ; empreinte exacte du texte ; état active/revoked. |
| facts | Au plus 32 dictionnaires : `id, subject, property, value, unit, polarity, scope, cardinality, source_id, source_version, source_sha256, span, origin, certainty`. |
| value | `{type, value}` contient du texte ou une **chaîne décimale** ; graphie et unité sont conservées. Pas de calcul ni conversion implicite. |
| span | `{start, end, text}` : chaque fait sélectionné exige une tranche exacte non vide de la version identifiée, en positions Unicode. |
| plan | `fact_ids` contient 1–8 identifiants sélectionnés uniques ; `required_ids` en est un sous-ensemble non vide. |
| contract | `language='fr'`, bornes de mots entières 1–10 000, `max_candidates` 1–64 et booléen `allow_repair`. |

Les identifiants suivent `[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}`. Subject/property/scope : non vides et ≤80 caractères ; valeur texte ≤160, unité ≤40, chaîne décimale ≤40. Les littéraux sont sans espace initial/final, à espaces simples, sans caractères de contrôle, substituts Unicode ou `[]«»`. L'unité est vide pour le texte. Les faits sélectionnés doivent être affirmés, monovalués et d'origine `document` ou `brief_fact` ; une `instruction` n'est jamais rendue comme fait. Les faits inutilisés bien formés ne subissent pas de validation sémantique. Les assertions opposées sélectionnées sont refusées de manière conservatrice ; aucun rapprochement de synonymes.

Les types JSON d'origine doivent être exacts : un booléen ne remplace pas un entier pour les offsets/bornes. La taille canonique de la requête est limitée à 262 144 octets, vérifiée avant encodage. `canonical(value)` reste un simple helper JSON : UTF-8, clés triées, `ensure_ascii=False`, séparateurs compacts et `allow_nan=False` ; il n'applique pas lui-même la borne de requête.

Forme positive compacte : `« subject » : « property » = VU ; portée « scope ». [source_id]`. La polarité négative utilise `≠`. Forme développée positive : `Pour la portée « scope », la propriété « property » de « subject » a pour valeur VU. [source_id]` ; négative : `n'a pas pour valeur`. V texte est entre guillemets ; une unité ajoute ` unité « unit »`. Ce sont les seules deux formulations. La réparation explore leurs combinaisons bornées et l'omission des faits facultatifs, sans retirer les faits requis ni utiliser de modèle. Un échec de cette grammaire/recherche ne prouve pas que l'intention est intrinsèquement impossible.

## Autorité, résultat et comptage

Le callback reçoit une copie des métadonnées aux étapes `before`/`after` autour du candidat retenu. Il renvoie exactement `{status, revision}` : `allowed` ou `revoked` avec révision identifiante ; `unavailable` avec `None`. Exceptions et réponses mal formées sont indisponibles. Un changement de révision refuse la sortie. Le callback est fourni par l'hôte ; l'exemple n'est ni une identité authentifiée ni une transaction de publication.

Le résultat contient statut/motif/corps, empreinte de requête, compte de mots, identifiants/couverture des faits, tentatives, contrôles d'autorité et provenance. Chaque segment lie empreinte du fait, identifiant/version/empreinte de source, extrait exact et positions/empreinte de sortie. Aucun corps factuel en cas d'échec. `semantic_status='not_evaluated'` et `publication_atomic=False` restent explicites. Les statuts distinguent `ok`, entrée invalide/non prise en charge/ambiguë, contrainte/recherche épuisée et refus d'autorité ; un résultat vide n'est pas automatiquement une information inconnue.

`OutputContract(min_words, max_words, language='fr', allowed_citation_ids=('brief',))` est immuable ; `from_mapping()`/`to_dict()` exposent des dictionnaires exacts. `validate_output(text, contract)` accepte ≤65 536 octets UTF-8. Il retire les citations complètes entre crochets puis compte les tokens séparés par des espaces Unicode. Apostrophes et traits d'union ne découpent pas les tokens. Corps vide, bornes, citations inconnues ou crochets mal formés provoquent un échec mécanique. La langue et la vérité sémantique ne sont pas évaluées. Les contrats/types invalides lèvent `ContractError`.

La même façade expose `make_initial_prompt`, `make_repair_prompt`, `VERSION`, `WORD_COUNT_RULE`, `MAX_TEXT_BYTES`, `MAX_PROMPT_BYTES`. Ces helpers construisent des chaînes locales sans appeler de fournisseur. Les plafonds de taille ne sont pas des quotas de mémoire du processus.

## Chargement vérifié

Les trois ressources source exactes et leur provenance MIT figurent dans `hermes_memory/ADMISSION-PROVENANCE.json` installé. Les façades utilisent un graphe partagé sous verrou, conservant l'identité des fonctions/classes. À chaque appel explicite de chargement, y compris en cache, le chargeur vérifie taille et SHA-256 des trois sources par des lectures limitées à la taille attendue plus un octet. Ressource absente/modifiée, nom interne occupé, cache incohérent ou construction échouée lèvent une `ImportError` générique. Une construction échouée retire uniquement ses propres enregistrements. Les homonymes de premier niveau ne sont pas exécutés.

Il s'agit d'un contrôle à la frontière du chargement, pas d'un bac à sable Python, d'une transaction de fichiers ou d'une vérification à chaque appel ultérieur. Les bootstraps conservés lisent normalement leurs fichiers frères installés. Ne pas modifier simultanément les ressources ou `sys.modules`. Les tests en processus neufs utilisent des copies jetables du paquet, jamais une installation active.
