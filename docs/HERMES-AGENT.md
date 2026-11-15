# Hermes Agent provider

[Français](HERMES-AGENT.fr.md) · [Operations surface](OPERATIONS.md) · [MCP server](MCP.md)

Nous Research's Hermes Agent accepts one external memory provider. Installing this package in Hermes Agent's environment registers `persistent-memory` through the `hermes_agent.memory_providers` entry point. Hermes Agent then gets the same memory as an MCP client, with two extras: validated memory is recalled before each turn, and a turn opens with a notice when something the conversation was shown is no longer valid.

## Enable it

In Hermes Agent's environment:

```sh
pip install /path/to/persistent-memory
```

In the profile's `config.yaml`:

```yaml
memory:
  provider: persistent-memory
```

The store is created in `$HERMES_HOME/persistent-memory/store` unless `store_dir` says otherwise.

## Configuration

`$HERMES_HOME/persistent-memory/config.json` (Hermes Agent's memory setup writes it too):

| Key | Default | Meaning |
| --- | --- | --- |
| `store_dir` | empty | Store directory. Point it at the store your MCP clients use to share one memory between Hermes Agent, Claude Code and others. |
| `workspace` | `hermes` | Workspace inside the store. |
| `prefetch` | `true` | Recall validated memory before each turn. |
| `top_k`, `max_context_chars` | `5`, `2000` | How much is recalled. |
| `allow_withdraw` | `true` | Expose `memory_withdraw`. |
| `qdrant_url`, `embed_url`, `embed_model` | empty | Optional [Qdrant projection](QDRANT.md); keys come from `PERSISTENT_MEMORY_QDRANT_API_KEY` and `PERSISTENT_MEMORY_EMBED_API_KEY`. |
| `qdrant_min_score`, `embed_query_prefix`, `embed_document_prefix` | `0.5`, empty, empty | Projection settings, see [QDRANT.md](QDRANT.md). |

## Behaviour

- **Tools**: the ten tools of the [MCP server](MCP.md), with the same schemas and refusals. Subagents and scheduled runs only get the five read tools.
- **Recall**: before each non-trivial turn, the provider searches the memory with the user's message and adds a block of validated entries, each with its `[artifact_id]`.
- **Notices**: when an entry shown to this Hermes session has since been withdrawn, invalidated or superseded, the next turn opens with a "No longer valid" block naming it, once.
- **Admission is explicit**: the provider never stores the conversation by itself. Something is stored only when the model calls `memory_remember`, `memory_derive`, `memory_correct` or `memory_learn`.

## Observed

On 14 November 2026, on Linux, with Hermes Agent and a local 9B model, the provider shared one store with an MCP server over HTTP and a Qdrant projection:

- `tests_integration/test_hermes_agent_manager.py`: all three tests passed inside Hermes Agent's `MemoryManager`, including entry-point discovery.
- Conversation 1: on request, the model stored a fact with `memory_remember`.
- Conversation 2: the fact was recalled before the turn and the answer cited `[preprod-port]`.
- Another client withdrew the fact through MCP over HTTP. Conversation 2, resumed: the provider's recall for that turn carried the notice (the ledger records its delivery to that session), and the model answered that no valid information was available.

Hermes Agent builds its tool routing table when the provider is added, before `initialize()`; the provider therefore announces its tools from the start.

## Tests

`tests/test_hermes_agent.py` drives the provider through a stand-in base class, so it runs without Hermes Agent; the shared adapter battery runs the same scenarios through it as through the other adapters. `tests_integration/test_hermes_agent_manager.py` runs it inside Hermes Agent's own `MemoryManager` and checks entry-point discovery; outside a Hermes Agent environment it reports its tests as skipped, with the reason.
