# Hermes Agent provenance provider

[Français](README.fr.md)

A memory provider for [Hermes Agent](https://github.com/NousResearch/hermes-agent) (Nous Research), built on the memory core of this repository. Hermes Agent keeps its built-in `MEMORY.md` and `USER.md`; this provider adds a long-term store whose every recall is revalidated at read time.

Distribution `hermes-agent-provenance` 0.1.0a1, module `hermes_agent_provenance`, provider name `provenance`. Alpha. It is an independent integration, not affiliated with Nous Research.

## What it does

- **Revalidated recall.** Before each turn, the provider searches the store and injects only items that the current authority still allows. A withdrawn or superseded source never reaches the model.
- **Explicit admission.** Nothing is stored automatically: `sync_turn` is deliberately empty. The model stores a fact only by calling `provenance_remember`.
- **Withdrawal notices per session.** The provider records which sources were shown to which Hermes session. When one of them is withdrawn, from this session or from anywhere else, the next turn of that session opens with a notice telling the model to stop relying on it, including on its own earlier answers. Each session is warned once per source.
- **Exposure report.** `hermes-provenance-exposure` lists every session that was shown a source which is withdrawn now. Exit code 1 when at least one session is exposed.

Tools exposed to the model:

| Tool | Effect |
|---|---|
| `provenance_search` | Lexical search of currently readable items, with `source_id` |
| `provenance_remember` | Admit one typed item (`observation`, `document`, `procedure`, `task`, `hypothesis`, `feedback`) |
| `provenance_withdraw` | Withdraw a source and everything derived from it. Not physical erasure |
| `provenance_explain` | Versions, readability and dependents of a source; metadata only |

Subagents and scheduled runs (`agent_context` other than `primary`) get the two read tools only.

## Install

The provider must be installed in the Python environment that runs Hermes Agent, next to the memory core. From a checkout of this repository:

```sh
python -m pip install . ./packages/hermes-agent-provider
```

Then select it in `config.yaml` of the Hermes profile, or with `hermes memory setup`:

```yaml
memory:
  provider: provenance
```

`hermes memory status` should list `provenance` as installed and active. Hermes Agent finds it through the `hermes_agent.memory_providers` entry point; no file is copied into Hermes.

Hermes Agent itself pins its dependencies for Python 3.14 and resolves them from its `uv.lock`. A source checkout installed with `uv sync --locked` (plus the `mcp` extra if MCP servers are used) worked; a plain `pip install -e` of the checkout did not resolve.

## Storage and settings

State lives under the profile, in `$HERMES_HOME/provenance/`: `authority/`, `anchor/`, `content.db`, `index.db` and `exposure.db`. Settings are read from `$HERMES_HOME/provenance/config.json`:

| Key | Default | Meaning |
|---|---|---|
| `workspace` | `hermes` | Memory workspace for this profile |
| `prefetch` | `true` | Recall before each turn |
| `top_k` | `5` | Items recalled per turn |
| `max_context_chars` | `2000` | Character budget of the recalled block |
| `allow_withdraw` | `true` | Offer `provenance_withdraw` to the model |

The recovery guarantees of the core require the authority and its freshness witness to be kept outside content-only backups; see [RECOVERY.md](../../docs/RECOVERY.md).

## Checks

`tests/` runs without Hermes Agent, using the stand-ins in `_compat.py`; it is part of the installed-distribution check of this repository (`scripts/check_distributions.py`). `tests_hermes_agent/` drives the provider through Hermes Agent's own `MemoryManager` and must be run from a Hermes Agent environment; elsewhere it reports SKIPPED with its reason.

One end-to-end observation, on one Linux host on 14 November 2026, with Hermes Agent at commit `d93e9ba4` and a local Qwen3.5-9B served by llama.cpp: in a single session, the agent stored a port number with `provenance_remember`, then answered it from the recalled block with its `source_id`. The source was then withdrawn outside the session. Asked again in the same session, whose history still contained the old answer twice, the agent replied that the information had been withdrawn, without calling a tool. This is one observation, not a benchmark.

## Limits

- The notice does not remove text from Hermes Agent's own session store, which keeps the transcript. Revocation controls future reads through this library only; it cannot recall what was already copied elsewhere.
- Search is lexical (FTS5). No embedding or semantic search.
- Hermes Agent allows one external memory provider at a time.
- Withdrawal blocks future reads; it is not physical erasure.
- The `agent` and `tools` modules are imported from Hermes Agent when available; a different package exposing those names would be taken for it.

MIT license, see [LICENSE](LICENSE). File provenance is recorded in [PROVENANCE.json](PROVENANCE.json).
