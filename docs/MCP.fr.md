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

Chaque schéma d'entrée refuse les arguments inconnus. Un argument facultatif envoyé à `null` ou vide (`""`, `[]`, `{}`) compte comme absent, car certains adaptateurs de frameworks envoient tous les champs non renseignés et certains modèles remplissent les champs inutilisés avec des valeurs vides. Un refus de la mémoire (`version_conflict`, `unknown_artifact`, `invalid_argument:text`, ...) revient comme résultat d'outil avec `isError: true`, que le modèle peut lire. À côté du code d'erreur, le résultat indique quand c'est possible comment corriger l'appel : `allowed_kinds`, `allowed_arguments`, `expected_type`, ou un `hint` pour les dates et les conflits de version. Un outil inconnu est une erreur JSON-RPC.

Les résultats sont du texte JSON ; à partir du protocole 2025-06-18, ils sont aussi envoyés en `structuredContent`.

## Avis

Un processus serveur est une session du registre. `memory_search` et `memory_read` notent ce que la session a vu. Quand l'une de ces versions est ensuite retirée, invalidée ou remplacée, par ce client ou par tout autre processus qui utilise la mémoire, le résultat d'outil suivant porte `memory_notices`, une fois par version. Les `instructions` du serveur demandent au modèle de ne plus s'appuyer dessus.

Un client qui garde le serveur actif d'une conversation à l'autre (c'est le cas de la passerelle d'Hermes Agent) partage une seule session entre elles. `--session` permet de choisir le nom soi-même.

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
