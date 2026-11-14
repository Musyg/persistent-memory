# Surface d'opérations

[English](OPERATIONS.md) · [README](../README.fr.md) · [API et service](API.fr.md)

`hermes_memory.persistent.PersistentMemory` réunit les opérations de la mémoire derrière une seule classe. Les adaptateurs (MCP, extensions d'agents, HTTP) l'appellent plutôt que le cœur, pour que chacun expose la même mémoire : sources, artefacts dérivés avec parents exacts, corrections, retrait en cascade, leçons et avis de retrait.

Elle n'ajoute aucune autorité. Chaque lecture passe toujours par `Memory.read` ou `Memory.validate` ; l'index de recherche et le registre sont des annexes qu'on peut supprimer et reconstruire.

## Ouvrir une mémoire

```python
from hermes_memory.persistent import PersistentMemory

memory = PersistentMemory("state/memory", "team-notes", create=True)
```

Un dossier contient une mémoire ; une mémoire peut contenir plusieurs espaces de travail. Sans `create=True`, une mémoire absente est refusée (`store_missing`) au lieu d'être créée en silence.

| Fichier | Rôle | Perte acceptable ? |
| --- | --- | --- |
| `authority/authority.db` | Versions, dépendances, retraits, chaîne d'événements | Non |
| `anchor/checkpoint.json` | Témoin de fraîcheur, gardé à part du contenu | Non |
| `content.db` | Contenu et projection lexicale du cœur | Non |
| `index.db` | Index de recherche, reconstruit depuis l'autorité | Oui |
| `ledger.db` | Expositions, avis, motifs de retrait, parents des leçons | Oui, les avis sont alors perdus |

## Les opérations

| # | Méthode | Ce qu'elle fait |
| --- | --- | --- |
| 1 | `read(ref, session=None)` | Lit une version exacte à travers l'autorité courante. Un refus renvoie la raison (`source_revoked`, `version_not_current`, `invalidated`, ...) et un état lisible (`withdrawn`, `superseded`, `invalidated`, ...). |
| 2 | `search(query, kinds=None, as_of=None, conditions=None, top_k=5, max_chars=2000, session=None)` | Ne renvoie que des versions courantes et lisibles. Les fenêtres de validité sont vérifiées à `as_of`, maintenant par défaut ; un élément avec préconditions demande des `conditions` correspondantes. Une requête de plus de huit mots garde ses mots de trois caractères ou plus. |
| 3 | `remember(text, kind="observation", source_id=None, aliases=None, valid_from=None, valid_until=None, observed_at=None, preconditions=None, confidence=None)` | Admet une nouvelle source. Un `source_id` existant est refusé (`version_conflict`) : utiliser `correct`. |
| 4 | `derive(text, parents, kind="procedure", artifact_id=None, expected_version=None, expected_epoch=None, ...)` | Enregistre un artefact construit à partir de versions parentes exactes. Un parent est une référence (relation `derives`) ou `{"ref": ..., "relation": "derives" \| "indexes" \| "cites"}`. Il faut au moins un parent `derives` ou `indexes`, lisible au moment de l'écriture. |
| 5 | `correct(artifact_id, text, expected_version, parents=None, ...)` | Comparer puis remplacer : la version courante n'est remplacée que si elle est encore `expected_version`. Les métadonnées non fournies sont conservées. Un artefact dérivé garde ses parents sauf si on en donne de nouveaux ; ils doivent être encore courants. |
| 6 | `explain(artifact_id_or_ref)` | Métadonnées seulement : type, lisibilité, parents, graphe amont, versions et dépendants. Ne renvoie jamais le contenu. |
| 7 | `plan_withdrawal(artifact_id)`, `withdraw(artifact_id, reason, event_id=None, session=None)` | Le plan liste ce qui serait bloqué. Retirer une source révoque toutes ses versions (idempotent par `event_id`) ; retirer un artefact dérivé invalide sa version courante. Dans les deux cas, tout ce qui en dérive par `derives` ou `indexes` cesse d'être lisible, et les projections sont purgées. Rien n'est effacé physiquement. |
| 8 | `learn(trace, feedback, lesson, kind="procedure", lesson_id=None, ...)` | Enregistre la trace d'une tâche et son retour comme sources brutes, puis dérive la leçon des deux. Seule la leçon est cherchable. Retirer la trace ou le retour bloque la leçon. Si la leçon ne peut pas être enregistrée, les deux parents sont révoqués aussitôt. |
| 9 | `record_exposure(session, refs, via)`, `notices(session, mark=True)`, `exposure_report()` | Le registre note quelles versions une session a vues (`read` et `search` le font si `session` est donné). `notices` renvoie, une seule fois chacune, les versions vues par cette session qui ne sont plus valides : retirées, invalidées ou remplacées par une correction. `exposure_report` liste toutes les sessions concernées. |

`OPERATIONS` donne la liste des méthodes, pour les adaptateurs qui les exposent.

Les refus lèvent `hermes_memory.core.MemoryError`, une `ValueError` dont le message est le code de raison. Les erreurs de stockage imprévues ne sont pas converties.

## Exemple

```python
memory = PersistentMemory("state/memory", "team-notes", create=True)

port = memory.remember("The test server listens on port 9300.", source_id="port")
note = memory.derive("Open 9300 on the test firewall.", parents=[port["ref"]], kind="procedure")

memory.search("firewall 9300", session="chat-1")          # la session voit la procédure
memory.correct("port", "The test server listens on port 9400.",
               expected_version=port["ref"]["version_id"])

memory.read(note["ref"])["state"]                        # "superseded" : son parent a changé
memory.notices("chat-1")["notices"]                       # prévient chat-1, une fois
```

Une leçon tirée de l'expérience :

```python
out = memory.learn(
    trace={"task": "export ledger as CSV", "attempt": "UTF-8 without BOM"},
    feedback={"success": False, "violation": "bom_required"},
    lesson="For this receiver, export CSV as UTF-8 with a BOM.",
)
memory.search("CSV receiver BOM", kinds=["procedure"])   # trouve la leçon, pas ses parents
memory.withdraw(out["feedback"]["artifact_id"], "feedback was wrong")   # la leçon est bloquée
```

## Limites

- Le cas testé est un seul processus à la fois par mémoire ; plusieurs processus sont sérialisés par SQLite mais ne font pas partie des tests de cette surface.
- L'index de recherche tient jusqu'à 5 000 artefacts courants par espace de travail et 32 Mio de contenu par reconstruction.
- `search` est lexicale (SQLite FTS5 plus alias exacts). `attach_projection` ajoute une projection vectorielle comme [Qdrant](QDRANT.fr.md) ; ses candidats sont revalidés contre l'autorité et fusionnés avec les candidats lexicaux.
- La complétude (`complete`) porte sur les candidats indexés à l'époque courante. Les sources de trace et de retour sont exclues de l'index exprès et ne rendent pas un résultat incomplet.
- Linux est la plateforme qualifiée pour cette version.
