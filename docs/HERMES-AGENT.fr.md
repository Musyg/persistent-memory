# Fournisseur Hermes Agent

[English](HERMES-AGENT.md) · [Surface d'opérations](OPERATIONS.fr.md) · [Serveur MCP](MCP.fr.md) · [Brancher vos outils](SETUP.fr.md)

Hermes Agent, de Nous Research, accepte un fournisseur de mémoire externe. Installer ce paquet dans l'environnement d'Hermes Agent enregistre `persistent-memory` par le point d'entrée `hermes_agent.memory_providers`. Hermes Agent reçoit alors la même mémoire qu'un client MCP, avec deux ajouts : la mémoire validée est rappelée avant chaque tour, et un tour s'ouvre sur un avis quand une chose montrée dans la conversation n'est plus valide.

## L'activer

Dans l'environnement d'Hermes Agent :

```sh
pip install persistent-memory-mcp
```

Puis, depuis cet environnement :

```sh
persistent-memory setup hermes-agent
```

Cette commande choisit le fournisseur et le fait pointer vers la mémoire de vos autres outils, espace `default` ([SETUP.fr.md](SETUP.fr.md)). Pour le faire à la main, dans le `config.yaml` du profil :

```yaml
memory:
  provider: persistent-memory
```

Configurée à la main, la mémoire est créée dans `$HERMES_HOME/persistent-memory/store`, sauf si `store_dir` indique un autre dossier.

## Configuration

`$HERMES_HOME/persistent-memory/config.json` (l'assistant de configuration de la mémoire d'Hermes Agent l'écrit aussi) :

| Clé | Défaut | Sens |
| --- | --- | --- |
| `store_dir` | vide | Dossier de la mémoire. Le faire pointer vers celle de vos clients MCP pour partager une seule mémoire entre Hermes Agent, Claude Code et les autres. |
| `workspace` | `hermes` | Espace de travail dans la mémoire. |
| `prefetch` | `true` | Rappeler la mémoire validée avant chaque tour. |
| `top_k`, `max_context_chars` | `5`, `2000` | Quantité rappelée. |
| `allow_withdraw` | `true` | Exposer `memory_withdraw`. |
| `qdrant_url`, `embed_url`, `embed_model` | vide | [Projection Qdrant](QDRANT.fr.md) facultative ; les clés viennent de `PERSISTENT_MEMORY_QDRANT_API_KEY` et `PERSISTENT_MEMORY_EMBED_API_KEY`. |
| `qdrant_min_score`, `embed_query_prefix`, `embed_document_prefix` | `0.5`, vide, vide | Réglages de la projection, voir [QDRANT.fr.md](QDRANT.fr.md). |

## Comportement

- **Outils** : les dix outils du [serveur MCP](MCP.fr.md), avec les mêmes schémas et les mêmes refus. Les sous-agents et les tâches planifiées n'ont que les cinq outils de lecture.
- **Rappel** : avant chaque tour non trivial, le fournisseur cherche dans la mémoire avec le message de l'utilisateur et ajoute un bloc d'entrées validées, chacune avec son `[artifact_id]`.
- **Avis** : quand une entrée montrée à cette session Hermes a depuis été retirée, invalidée ou remplacée, le tour suivant s'ouvre sur un bloc « No longer valid » qui la nomme, une seule fois.
- **Admission explicite** : le fournisseur n'enregistre jamais la conversation de lui-même. Une chose n'est enregistrée que si le modèle appelle `memory_remember`, `memory_derive`, `memory_correct` ou `memory_learn`.

## Observé

Le 14 novembre 2026, sous Linux, avec Hermes Agent et un modèle local de 9 milliards de paramètres, le fournisseur partageait une mémoire avec un serveur MCP en HTTP et une projection Qdrant :

- `tests_integration/test_hermes_agent_manager.py` : les trois tests ont réussi dans le `MemoryManager` d'Hermes Agent, découverte du point d'entrée comprise.
- Conversation 1 : à la demande, le modèle a enregistré un fait avec `memory_remember`.
- Conversation 2 : le fait a été rappelé avant le tour et la réponse citait `[preprod-port]`.
- Un autre client a retiré le fait par MCP en HTTP. Conversation 2 reprise : le rappel du fournisseur pour ce tour portait l'avis (le registre note sa remise à cette session), et le modèle a répondu qu'aucune information valide n'était disponible.

Hermes Agent construit sa table de routage des outils quand le fournisseur est ajouté, avant `initialize()` ; le fournisseur annonce donc ses outils dès le départ.

## Tests

`tests/test_hermes_agent.py` pilote le fournisseur par une classe de base de remplacement, donc sans Hermes Agent ; la batterie commune des adaptateurs lui fait passer les mêmes scénarios qu'aux autres. `tests_integration/test_hermes_agent_manager.py` le fait tourner dans le `MemoryManager` d'Hermes Agent et vérifie la découverte du point d'entrée ; hors d'un environnement Hermes Agent, ses tests sont signalés comme sautés, avec la raison.
