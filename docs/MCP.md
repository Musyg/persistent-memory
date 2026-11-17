# MCP server

[Français](MCP.fr.md) · [Operations surface](OPERATIONS.md) · [Connect your tools](SETUP.md) · [README](../README.md)

`persistent-memory-mcp` serves the [operations surface](OPERATIONS.md) to any MCP client, over stdio or Streamable HTTP. It uses the Python standard library only. Every tool goes through `PersistentMemory`, so a client sees the whole memory: exact versions, derived artifacts, corrections, withdrawal with cascade, lessons and withdrawal notices.

## Start it

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/persistent-memory-mcp --store ~/.persistent-memory --create
```

The client starts this command itself; you only put it in the client's configuration. `persistent-memory setup <client>` writes that configuration for you; see [SETUP.md](SETUP.md).

| Option | Meaning |
| --- | --- |
| `--store DIR` | Store directory. Default: `$PERSISTENT_MEMORY_DIR`, else the platform data folder ([SETUP.md](SETUP.md)). |
| `--workspace NAME` | Workspace inside the store. Default: `$PERSISTENT_MEMORY_WORKSPACE` or `default`. |
| `--create` | Create the store if it does not exist. Without it, a missing store stops the server with a message on stderr. |
| `--read-only` | Only `memory_search`, `memory_read`, `memory_explain`, `memory_plan_withdrawal` and `memory_notices`. |
| `--no-withdraw` | Everything except `memory_withdraw`. |
| `--review` | Writes become proposals that a person approves; see [Review mode](#review-mode). Not combined with `--read-only`. |
| `--session ID` | Ledger session name for stdio. Default: a new one for each process. |
| `--transport http`, `--host`, `--port` | Serve Streamable HTTP on `/mcp` instead of stdio. Default `127.0.0.1:8766`. |
| `--token-file FILE` | Bearer token, read from a file only its owner can read. Required off loopback. |
| `--allow-origin URL` | Browser origin allowed to call the HTTP endpoint; repeatable. Default: none. |
| `--qdrant-url`, `--embed-url`, `--embed-model` | Optional [Qdrant projection](QDRANT.md) fused into `memory_search`. |

`python -m hermes_memory.mcp_server` and `persistent-memory mcp` are the same program.

## Tools

| Tool | Operation | Annotations |
| --- | --- | --- |
| `memory_search` | Current, valid versions only, with `artifact_id`, exact `ref`, kind and metadata | read-only |
| `memory_read` | One exact version, or the reason it is refused | read-only |
| `memory_remember` | New source | |
| `memory_derive` | Artifact made from exact parents | |
| `memory_correct` | Compare-and-swap correction | |
| `memory_explain` | Parents, dependents, readability; no content | read-only |
| `memory_plan_withdrawal` | What a withdrawal would block | read-only |
| `memory_withdraw` | Withdrawal with cascade, idempotent with `event_id` | destructive |
| `memory_learn` | Lesson from a task trace and its feedback | |
| `memory_notices` | What this session saw that is no longer valid | read-only |
| `memory_proposal_status` | With `--review` only: where proposals stand | read-only |

Every input schema refuses unknown arguments. An optional argument sent as `null` or empty (`""`, `[]`, `{}`) counts as absent, because some framework adapters send every unset field and some models fill unused fields with empty values. A refusal from the memory (`version_conflict`, `unknown_artifact`, `invalid_argument:text`, ...) comes back as a tool result with `isError: true`, so the model can read it. Next to the error code, the result says how to correct the call where it can: `allowed_kinds`, `allowed_arguments`, `expected_type` with its `minimum` and `maximum`, or a `hint` for timestamps and version conflicts. A number outside the range its schema advertises is refused rather than applied. An unknown tool is a JSON-RPC error.

Results are JSON text; from protocol 2025-06-18 on they are also sent as `structuredContent`.

## Notices

One server process is one ledger session. `memory_search` and `memory_read` record what the session was shown. When one of those versions is later withdrawn, invalidated or superseded, by this client or any other process using the store, the next tool result carries `memory_notices`, once per version. The server's `instructions` ask the model to stop relying on them.

A client that keeps the server running across conversations (Hermes Agent's gateway does) shares one session across them. Use `--session` to choose the name yourself.

## Near-duplicates

After `memory_remember`, `memory_derive` or `memory_learn`, the server looks for current entries worded almost the same way: at least 60% of their words in common (Jaccard overlap of the word sets), the new entry and its parents left out. When it finds some, the result also carries `similar` (up to three entries, with `artifact_id`, `ref`, `text` and `overlap`) and `similar_hint`, which tells the model to keep a single entry with `memory_correct` or `memory_withdraw`. Nothing is merged and the write is not refused. The usual case is an agent that remembers "port 6544" next to "port 6543" instead of correcting the first.

The entries shown this way count as seen by the session, so a later withdrawal brings a notice. The check uses keyword search: a paraphrase with other words is not reported. In review mode, the proposal carries `similar` too, for the person who approves it. From Python, `hermes_memory.mcp_server.similar_entries(memory, text)` runs the same check.

## Review mode

With `--review`, the agent can search and read as usual, but `memory_remember`, `memory_derive`, `memory_correct`, `memory_withdraw` and `memory_learn` no longer change the memory. Each call is checked against its schema, then kept as a pending proposal in `review.db`, in the store folder. The result is `{"status": "pending_review", "proposal_id": ...}`. One more tool, `memory_proposal_status`, tells the agent where its proposals stand. No tool can approve: the decision is taken outside the server, by a person.

```sh
persistent-memory review                 # pending proposals, all workspaces
persistent-memory review show p-...      # the full proposed call
persistent-memory review approve p-...   # apply it
persistent-memory review reject p-... --note "not confirmed"
```

`review` takes `--store` like the other commands, `--workspace` to list one workspace, `--all` to list decided proposals too, and `--json`.

Approval runs the proposed call through the same code as a direct call, so it keeps every guarantee: exact versions, compare-and-swap on corrections, cascade and notices on withdrawal. A proposal the memory refuses at that moment is marked `failed` with the refusal code, and `approve` exits with status 3. The usual case is a correction whose `expected_version` is no longer current because another correction was approved first: it fails with `version_conflict` and is not forced through. A withdrawal without `event_id` gets `review-<proposal id>`, so the same proposal cannot withdraw twice. Each proposal is decided once; a second decision is refused with `proposal_already_<state>`. If approval stops on an I/O error, the proposal stays `applying` and nothing retries it on its own.

The server's `instructions` tell the model that writes wait for approval. `memory_proposal_status` without an id lists the latest proposals of the session; with an id, it shows any proposal of the same workspace.

## HTTP transport

`--transport http` serves one endpoint, `/mcp`. A POST carries one JSON-RPC message and gets a JSON answer; `initialize` returns an `Mcp-Session-Id` header that later requests repeat; DELETE ends the session; GET answers 405 because the server never opens a stream. Each MCP session is its own ledger session, so notices go to the client that saw a version.

On loopback no token is needed. Off loopback the server refuses to start without `--token-file`, and every request must carry `Authorization: Bearer <token>`. Requests with a browser `Origin` header are refused unless that origin is allowed. Bodies are limited to 4 MiB and the server keeps at most 256 sessions, idle ones expiring after a day.

On Linux and macOS the token file must be readable by its owner only. Windows has no such mode bits and the file's access list is not inspected: keep the token file in your own profile folder.

Hermes Agent, with the server already running:

```yaml
mcp_servers:
  memory:
    url: http://127.0.0.1:8766/mcp
```

## Client configuration

Claude Code, in a project's `.mcp.json` or a file passed with `--mcp-config`:

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

Hermes Agent (Nous Research), in `$HERMES_HOME/config.yaml`; the tools appear in the `mcp-memory` toolset:

```yaml
mcp_servers:
  memory:
    command: /path/to/.venv/bin/persistent-memory-mcp
    args: ["--store", "/home/me/.persistent-memory", "--create", "--workspace", "hermes"]
    timeout: 60
```

Any other MCP client: a stdio server with that command and those arguments. For the clients listed in [SETUP.md](SETUP.md), `persistent-memory setup` writes this for you.

## Protocol

- Newline-delimited JSON-RPC 2.0 on stdin and stdout; logs on stderr only.
- Protocol versions 2025-11-25, 2025-06-18 and 2025-03-26; an unknown requested version gets 2025-11-25.
- `server/discover` answers "method not found", so clients that probe for the 2026 discovery handshake fall back to `initialize`.
- Only `tools` is offered. Batches are refused. A message is limited to 4 MiB.

## Observed with real clients

On 14 November 2026, on Linux:

- Official MCP Python SDK 2.3.0 (stdio client): protocol 2025-11-25 negotiated, ten tools listed, remember, derive, search, withdraw with cascade, notices, refusal of an unknown argument and a lesson round trip.
- Claude Code 2.1.289: the server connected and its ten tools were listed. The model turn itself did not run because that machine's Claude sign-in had expired.
- Hermes Agent with a local 9B model: the tools were registered in `mcp-memory`; a fact was stored, found again in a later conversation with its `artifact_id`, and withdrawn on request. A small model sometimes calls a tool without its required argument first; Hermes Agent rejects that call and the model retries.

Over HTTP (`--transport http`), with the official MCP Python SDK 2.3.0: 2025-11-25 negotiated, ten tools listed, a semantic search through the [Qdrant projection](QDRANT.md), a withdrawal with its notice. Hermes Agent's provider and this server shared the same store; see [HERMES-AGENT.md](HERMES-AGENT.md).

These are interoperability checks, not quality measurements.
