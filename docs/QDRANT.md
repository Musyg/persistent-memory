# Qdrant projection

[Français](QDRANT.fr.md) · [Operations surface](OPERATIONS.md) · [MCP server](MCP.md)

Lexical search finds the words you typed. A vector projection also finds what you meant: "firewall" can find a note about the "pare-feu". `hermes_memory.qdrant_projection` adds Qdrant as that projection, through Qdrant's REST API and the Python standard library only; no client library is needed.

## What it guarantees

- **Qdrant never holds content.** A point carries a vector and an exact ref (workspace, artifact, version) and nothing else.
- **Qdrant only proposes.** Every candidate is read again through the authority, then filtered by kind, validity window and preconditions exactly like a lexical candidate. A withdrawn, superseded or invalidated version is refused even if its vector is still in Qdrant.
- **Qdrant follows the authority.** After each write, points of versions that are no longer readable are deleted and new readable versions are added. If Qdrant is down, the write still succeeds, the projection is marked `unavailable`, and the next synchronization catches up.
- **A tampered point is ignored.** A point id is derived from its ref; a payload that does not match its id is dropped.
- **Lesson parents stay out.** Task traces and feedback are not embedded; only lessons and ordinary entries are.

## Use it

You need a Qdrant server and an OpenAI-compatible `/embeddings` endpoint (OpenAI, llama.cpp server, Ollama, vLLM, text-embeddings-inference...).

```python
from hermes_memory.persistent import PersistentMemory
from hermes_memory.qdrant_projection import OpenAIEmbeddings, QdrantProjection

memory = PersistentMemory("state/memory", "team-notes", create=True)
embed = OpenAIEmbeddings("http://127.0.0.1:8000/v1", "nomic-embed-text", api_key_env="EMBED_KEY")
memory.attach_projection(QdrantProjection(memory, "http://127.0.0.1:6333", embed, min_score=0.5))
memory.search("which port does the test machine use")
```

`search` then fuses lexical and vector candidates (reciprocal rank fusion) and reports the projection's state under `semantic`. With the MCP server:

```sh
persistent-memory-mcp --store ~/.persistent-memory --create \
  --qdrant-url http://127.0.0.1:6333 \
  --embed-url http://127.0.0.1:8000/v1 --embed-model nomic-embed-text \
  --embed-query-prefix "search_query: " --embed-document-prefix "search_document: " --qdrant-min-score 0.3
```

API keys are read from environment variables named by `--qdrant-api-key-env` and `--embed-api-key-env`, never from the command line. The Hermes Agent provider takes the same settings as `qdrant_url`, `embed_url` and `embed_model` in its configuration.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `collection` | `persistent-memory-<workspace>-<model hash>` | Changing the embedding model uses a new collection. |
| `min_score` | `0.5` | Cosine score below which a candidate counts as unrelated. Vector search always has a nearest neighbour; this keeps it from filling results with noise. Tune it per model. |
| `query_prefix`, `document_prefix` | empty | Text put before queries and entries before embedding, for models that expect task prefixes (`search_query: ` / `search_document: `, `query: ` / `passage: `). |

Up to 5,000 current entries per workspace are projected, as for the lexical index.

## Observed

On 14 November 2026, on Linux, against a disposable Qdrant 1.20.0 server and the `nomic-embed-text-v2-moe` model served through an OpenAI-compatible endpoint:

- `tests_integration/test_qdrant_server.py`: all three tests passed (lifecycle on a real server, stale point refused by revalidation, paraphrase found then withdrawn).
- With this model and the prefixes `search_query: ` / `search_document: `, a related question scored about 0.33 and unrelated entries 0.08 to 0.11, so `min_score` 0.3 was used. With the default 0.5 nothing would have matched: tune it for your model.
- Through `persistent-memory-mcp --transport http` and the official MCP Python SDK 2.3.0: a paraphrased question with no word in common found the entry, and after withdrawal it was no longer returned.

These are integration checks on a handful of entries, not a retrieval-quality measurement.

## Tests

`tests/test_qdrant_projection.py` and the shared adapter battery run against an in-process stand-in for the REST calls. `tests_integration/test_qdrant_server.py` runs against a real, disposable Qdrant server and optionally a real embedding model; without them it reports its tests as skipped, with the reason.
