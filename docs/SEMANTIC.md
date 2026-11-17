# Search by meaning, locally

[Français](SEMANTIC.fr.md) · [MCP server](MCP.md) · [Qdrant projection](QDRANT.md)

Keyword search finds the words you typed. With `--semantic`, `memory_search` also finds what you meant: "what is the pet's name" finds "The cat is called Mika", and "quand est-ce qu'on déploie" finds "Deploys happen on Tuesdays". Nothing else to run: the vectors sit in `vectors.db`, in the store folder, and the model runs inside the server process.

```sh
pip install "persistent-memory-mcp[semantic]"
persistent-memory-mcp --semantic --create < /dev/null    # first run: downloads the model, then exits
```

In Windows `cmd`, write `< NUL` instead of `< /dev/null`.

The base install is unchanged and has no dependency. The `semantic` extra adds [fastembed](https://github.com/qdrant/fastembed), which runs an ONNX model on the CPU, and numpy with it.

## What it guarantees

The local projection follows the same rules as the [Qdrant projection](QDRANT.md):

- **Vectors, never text.** A row of `vectors.db` holds a vector and an exact ref (workspace, artifact, version).
- **It only proposes.** Every candidate is read again through the authority, then filtered by kind, validity window and preconditions exactly like a keyword candidate. A withdrawn, superseded or invalidated version is refused even if its vector is still there.
- **It follows the authority.** After each write, vectors of versions that are no longer readable are deleted and new readable versions are embedded. Only new versions are embedded.
- **A forged row is ignored.** A row's id is derived from its ref; a row whose ref does not match its id is dropped.
- **It can fail without harm.** If the model cannot be downloaded or loaded, if it fails on a text, or if `vectors.db` cannot be read, the projection is marked `unavailable`, the write is kept and keyword search goes on. A model that failed to load is tried again after five minutes, not at every write. A corrupt `vectors.db` is rebuilt, and so is one deleted while the server runs. If the extra is not installed, the server does not start and says which package is missing.

## Connect a client

Add `--semantic` to the server's arguments in the client configuration that `persistent-memory setup` wrote, for example in Claude Code's `.mcp.json` or Claude Desktop's `claude_desktop_config.json`:

```json
"args": ["-m", "hermes_memory.mcp_server", "--store", "...", "--workspace", "default", "--semantic"]
```

Setting `PERSISTENT_MEMORY_SEMANTIC=1` in the server's environment does the same. Run the warm-up command above once first: the first start downloads about 1 GB, and some clients stop waiting for a server after a minute. Later starts load the model from `models/` in the store folder, in a few seconds.

## Settings

| Option | Default | Meaning |
| --- | --- | --- |
| `--semantic` | off | Fuse a local vector search into `memory_search` |
| `--embed-model` | `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | A model fastembed supports |
| `--semantic-min-score` | 0.3 with the default model, 0.5 otherwise | Cosine score below which a candidate is ignored |
| `--embed-url` | none | Use an OpenAI-compatible `/embeddings` endpoint instead of the in-process model; needs `--embed-model` |
| `--embed-query-prefix`, `--embed-document-prefix` | empty | For models that expect a task prefix |

With `--embed-url` the extra is not needed: the server calls the endpoint with the standard library. For example, with Ollama on the same machine:

```sh
persistent-memory-mcp --semantic --embed-url http://127.0.0.1:11434/v1 --embed-model nomic-embed-text \
  --embed-query-prefix "search_query: " --embed-document-prefix "search_document: "
```

`--semantic` and `--qdrant-url` cannot be combined. Changing the model starts a new set of vectors; the old ones stay in `vectors.db` until you delete the file, which is always safe: it is rebuilt by the next write or start. If the model behind the same name starts giving vectors of another size, its vectors are rebuilt. Vectors are stored as little-endian float32, so the file reads the same on any machine.

## Choosing the model

Measured on 17 November 2026 in a Linux cloud container (x86_64, CPU only), fastembed 0.9.1. Twelve synthetic facts in English and French, twelve questions that each match one fact without sharing its key words, four unrelated questions. The set is small: read it as an indication, not a benchmark.

| Model | License | Download | Right fact ranked first | Lowest score of a right fact | Highest score of an unrelated question | Time per query |
| --- | --- | --- | --- | --- | --- | --- |
| paraphrase-multilingual-mpnet-base-v2 (default) | Apache-2.0 | 1.0 GB | 12 of 12 | 0.25 | 0.22 | 20 ms |
| paraphrase-multilingual-MiniLM-L12-v2 | Apache-2.0 | 0.22 GB | 10 of 12 | 0.15 | 0.21 | 8 ms |
| google/embeddinggemma-300m | Gemma terms | 1.24 GB | 12 of 12 | 0.47 | 0.37 | 33 ms |
| Qwen/Qwen3-Embedding-0.6B-Q | Apache-2.0 | 1.12 GB | 11 of 12 | 0.40 | 0.42 | 221 ms |

The default has the best ranking under a permissive license. Its threshold of 0.3 keeps unrelated questions out at the cost of the hardest matches, which keyword search may still find. MiniLM is a smaller download. embeddinggemma separates related from unrelated questions more clearly; use it with `--embed-model google/embeddinggemma-300m --semantic-min-score 0.42` if its terms suit you.

## Limits

- Up to 5,000 current entries per workspace, like the search index. Scoring reads every vector of the workspace: about 0.2 s for 5,000 vectors of 768 dimensions in pure Python on the container above, less with numpy, which the extra installs.
- Task traces and feedback are not embedded; lessons and ordinary entries are.
- The model runs on the CPU. The first start downloads it; plan for the disk space in the store folder.
