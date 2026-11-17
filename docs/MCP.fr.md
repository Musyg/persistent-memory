# Serveur MCP

[English](MCP.md) · [Surface d'opérations](OPERATIONS.fr.md) · [Brancher vos outils](SETUP.fr.md) · [README](../README.fr.md)

`persistent-memory-mcp` sert la [surface d'opérations](OPERATIONS.fr.md) à tout client MCP, en stdio ou en HTTP (Streamable HTTP). Il n'utilise que la bibliothèque standard de Python. Chaque outil passe par `PersistentMemory` : un client voit donc toute la mémoire, avec versions exactes, artefacts dérivés, corrections, retrait en cascade, leçons et avis de retrait.

## Le lancer

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/persistent-memory-mcp --store ~/.persistent-memory --create
```

C'est le client qui lance cette commande ; il suffit de la mettre dans sa configuration. `persistent-memory setup <client>` écrit cette configuration pour vous ; voir [SETUP.fr.md](SETUP.fr.md).

| Option | Sens |
| --- | --- |
| `--store DIR` | Dossier de la mémoire. Par défaut : `$PERSISTENT_MEMORY_DIR`, sinon le dossier de données du système ([SETUP.fr.md](SETUP.fr.md)). |
| `--workspace NAME` | Espace de travail dans la mémoire. Par défaut : `$PERSISTENT_MEMORY_WORKSPACE` ou `default`. |
| `--create` | Crée la mémoire si elle n'existe pas. Sans cette option, une mémoire absente arrête le serveur avec un message sur stderr. |
| `--read-only` | Seulement `memory_search`, `memory_read`, `memory_explain`, `memory_plan_withdrawal` et `memory_notices`. |
| `--no-withdraw` | Tout sauf `memory_withdraw`. |
| `--review` | Les écritures deviennent des propositions qu'une personne approuve ; voir [Mode validation](#mode-validation). Pas avec `--read-only`. |
| `--session ID` | Nom de la session dans le registre, en stdio. Par défaut : un nouveau à chaque processus. |
| `--transport http`, `--host`, `--port` | Sert le HTTP sur `/mcp` au lieu de stdio. Par défaut `127.0.0.1:8766`. |
| `--token-file FILE` | Jeton porteur, lu dans un fichier que seul son propriétaire peut lire. Obligatoire hors boucle locale. |
| `--allow-origin URL` | Origine de navigateur autorisée à appeler le point HTTP ; répétable. Par défaut : aucune. |
| `--qdrant-url`, `--embed-url`, `--embed-model` | [Projection Qdrant](QDRANT.fr.md) facultative, fusionnée dans `memory_search`. |

`python -m hermes_memory.mcp_server` et `persistent-memory mcp` lancent le même programme.

## Outils

| Outil | Opération | Annotations |
| --- | --- | --- |
| `memory_search` | Versions courantes et valides seulement, avec `artifact_id`, `ref` exacte, type et métadonnées | lecture seule |
| `memory_read` | Une version exacte, ou la raison de son refus | lecture seule |
| `memory_remember` | Nouvelle source | |
| `memory_derive` | Artefact construit à partir de parents exacts | |
| `memory_correct` | Correction qui compare la version attendue | |
| `memory_explain` | Parents, dépendants, lisibilité ; aucun contenu | lecture seule |
| `memory_plan_withdrawal` | Ce qu'un retrait bloquerait | lecture seule |
| `memory_withdraw` | Retrait en cascade, idempotent avec `event_id` | destructif |
| `memory_learn` | Leçon tirée de la trace d'une tâche et de son retour | |
| `memory_notices` | Ce que cette session a vu et qui n'est plus valide | lecture seule |
| `memory_proposal_status` | Avec `--review` seulement : où en sont les propositions | lecture seule |

Chaque schéma d'entrée refuse les arguments inconnus. Un argument facultatif envoyé à `null` ou vide (`""`, `[]`, `{}`) compte comme absent, car certains adaptateurs de frameworks envoient tous les champs non renseignés et certains modèles remplissent les champs inutilisés avec des valeurs vides. Un refus de la mémoire (`version_conflict`, `unknown_artifact`, `invalid_argument:text`, ...) revient comme résultat d'outil avec `isError: true`, que le modèle peut lire. À côté du code d'erreur, le résultat indique quand c'est possible comment corriger l'appel : `allowed_kinds`, `allowed_arguments`, `expected_type` avec son `minimum` et son `maximum`, ou un `hint` pour les dates et les conflits de version. Un nombre hors de l'intervalle annoncé par son schéma est refusé au lieu d'être appliqué. Un outil inconnu est une erreur JSON-RPC.

Les résultats sont du texte JSON ; à partir du protocole 2025-06-18, ils sont aussi envoyés en `structuredContent`.

## Avis

Un processus serveur est une session du registre. `memory_search` et `memory_read` notent ce que la session a vu. Quand l'une de ces versions est ensuite retirée, invalidée ou remplacée, par ce client ou par tout autre processus qui utilise la mémoire, le résultat d'outil suivant porte `memory_notices`, une fois par version. Les `instructions` du serveur demandent au modèle de ne plus s'appuyer dessus.

Un client qui garde le serveur actif d'une conversation à l'autre (c'est le cas de la passerelle d'Hermes Agent) partage une seule session entre elles. `--session` permet de choisir le nom soi-même.

## Quasi-doublons

Après `memory_remember`, `memory_derive` ou `memory_learn`, le serveur cherche les entrées courantes formulées presque de la même façon : au moins 60 % de mots en commun (recouvrement de Jaccard des ensembles de mots), sans compter la nouvelle entrée ni ses parents. S'il en trouve, le résultat porte aussi `similar` (jusqu'à trois entrées, avec `artifact_id`, `ref`, `text` et `overlap`) et `similar_hint`, qui invite le modèle à ne garder qu'une entrée avec `memory_correct` ou `memory_withdraw`. Rien n'est fusionné et l'écriture n'est pas refusée. Le cas courant est un agent qui retient « port 6544 » à côté de « port 6543 » au lieu de corriger la première entrée.

Les entrées montrées ainsi comptent comme vues par la session : un retrait ultérieur donne donc un avis. La vérification passe par la recherche par mots-clés : une paraphrase avec d'autres mots n'est pas signalée. En mode validation, la proposition porte aussi `similar`, pour la personne qui l'approuve. En Python, `hermes_memory.mcp_server.similar_entries(memory, text)` fait la même vérification.

## Mode validation

Avec `--review`, l'agent cherche et lit comme d'habitude, mais `memory_remember`, `memory_derive`, `memory_correct`, `memory_withdraw` et `memory_learn` ne modifient plus la mémoire. Chaque appel est vérifié contre son schéma, puis gardé comme proposition en attente dans `review.db`, dans le dossier de la mémoire. Le résultat est `{"status": "pending_review", "proposal_id": ...}`. Un outil de plus, `memory_proposal_status`, indique à l'agent où en sont ses propositions. Aucun outil ne peut approuver : la décision se prend hors du serveur, par une personne.

```sh
persistent-memory review                 # propositions en attente, tous espaces
persistent-memory review show p-...      # l'appel proposé en entier
persistent-memory review approve p-...   # l'appliquer
persistent-memory review reject p-... --note "pas confirmé"
```

`review` accepte `--store` comme les autres commandes, `--workspace` pour un seul espace, `--all` pour lister aussi les propositions tranchées, et `--json`.

L'approbation fait passer l'appel proposé par le même code qu'un appel direct, avec toutes les garanties : versions exactes, comparaison de version sur les corrections, cascade et avis sur les retraits. Une proposition que la mémoire refuse à ce moment-là passe à l'état `failed` avec le code du refus, et `approve` sort avec le statut 3. Le cas courant est une correction dont la `expected_version` n'est plus la version courante, parce qu'une autre correction a été approuvée avant : elle échoue avec `version_conflict` et n'est pas appliquée de force. Un retrait sans `event_id` reçoit `review-<id de la proposition>`, si bien qu'une même proposition ne peut pas retirer deux fois. Chaque proposition se tranche une seule fois ; une seconde décision est refusée avec `proposal_already_<état>`. Si l'approbation s'arrête sur une erreur d'entrée-sortie, la proposition reste `applying` et rien ne la relance tout seul.

Les `instructions` du serveur préviennent le modèle que les écritures attendent une validation. `memory_proposal_status` sans identifiant liste les dernières propositions de la session ; avec un identifiant, il montre toute proposition du même espace.

## Transport HTTP

`--transport http` sert un seul point, `/mcp`. Un POST porte un message JSON-RPC et reçoit une réponse JSON ; `initialize` renvoie un en-tête `Mcp-Session-Id` que les requêtes suivantes répètent ; DELETE termine la session ; GET répond 405, car le serveur n'ouvre jamais de flux. Chaque session MCP est sa propre session du registre : les avis vont au client qui a vu une version.

En boucle locale, aucun jeton n'est nécessaire. Hors boucle locale, le serveur refuse de démarrer sans `--token-file`, et chaque requête doit porter `Authorization: Bearer <jeton>`. Les requêtes avec un en-tête `Origin` de navigateur sont refusées, sauf origine autorisée. Les corps sont limités à 4 Mio et le serveur garde au plus 256 sessions ; une session inactive expire après un jour.

Sous Linux et macOS, le fichier du jeton doit être lisible par son seul propriétaire. Windows n'a pas ces droits et la liste d'accès du fichier n'est pas inspectée : gardez le fichier du jeton dans votre propre dossier de profil.

Hermes Agent, avec le serveur déjà lancé :

```yaml
mcp_servers:
  memory:
    url: http://127.0.0.1:8766/mcp
```

## Configuration des clients

Claude Code, dans le `.mcp.json` d'un projet ou un fichier passé avec `--mcp-config` :

```json
{
  "mcpServers": {
    "memory": {
      "command": "/path/to/.venv/bin/persistent-memory-mcp",
      "args": ["--store", "/home/me/.persistent-memory", "--create"]
    }
  }
}
```

Hermes Agent (Nous Research), dans `$HERMES_HOME/config.yaml` ; les outils apparaissent dans le jeu d'outils `mcp-memory` :

```yaml
mcp_servers:
  memory:
    command: /path/to/.venv/bin/persistent-memory-mcp
    args: ["--store", "/home/me/.persistent-memory", "--create", "--workspace", "hermes"]
    timeout: 60
```

Tout autre client MCP : un serveur stdio avec cette commande et ces arguments. Pour les clients listés dans [SETUP.fr.md](SETUP.fr.md), `persistent-memory setup` l'écrit pour vous.

## Protocole

- JSON-RPC 2.0, un message par ligne sur stdin et stdout ; journaux sur stderr uniquement.
- Versions 2025-11-25, 2025-06-18 et 2025-03-26 ; une version demandée inconnue reçoit 2025-11-25.
- `server/discover` répond « méthode introuvable », ce qui ramène les clients qui sondent la découverte de 2026 vers `initialize`.
- Seuls les outils (`tools`) sont proposés. Les lots sont refusés. Un message est limité à 4 Mio.

## Observé avec de vrais clients

Le 14 novembre 2026, sous Linux :

- SDK MCP officiel pour Python 2.3.0 (client stdio) : protocole 2025-11-25 négocié, dix outils listés ; mémorisation, dérivation, recherche, retrait en cascade, avis, refus d'un argument inconnu et leçon vérifiés de bout en bout.
- Claude Code 2.1.289 : le serveur s'est connecté et ses dix outils ont été listés. Le tour du modèle n'a pas tourné, la connexion Claude de cette machine avait expiré.
- Hermes Agent avec un modèle local de 9 milliards de paramètres : les outils ont été enregistrés dans `mcp-memory` ; un fait a été mémorisé, retrouvé avec son `artifact_id` dans une conversation suivante, puis retiré à la demande. Un petit modèle appelle parfois un outil sans son argument obligatoire ; Hermes Agent refuse l'appel et le modèle recommence.

En HTTP (`--transport http`), avec le SDK MCP officiel pour Python 2.3.0 : 2025-11-25 négocié, dix outils listés, une recherche sémantique par la [projection Qdrant](QDRANT.fr.md), un retrait avec son avis. Le fournisseur Hermes Agent et ce serveur partageaient la même mémoire ; voir [HERMES-AGENT.fr.md](HERMES-AGENT.fr.md).

Ce sont des contrôles d'interopérabilité, pas des mesures de qualité.
