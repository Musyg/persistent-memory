# Remote MCP endpoint

[Français](README.fr.md)

`hermes-memory-mcp` serves the provenance memory store over MCP's Streamable HTTP transport, so any MCP client that accepts a URL and a bearer token can search it, add to it and withdraw from it. Python standard library only, like the memory core.

Distribution `hermes-memory-mcp` 0.1.0a1, command `hermes-memory-mcp`. Alpha.

It uses the same store and exposure ledger as the [Hermes Agent provider](../hermes-agent-provider/README.md). Pointed at the same directory, a source withdrawn through MCP also warns the Hermes Agent sessions that were shown it, and the reverse.

## Tools

| Tool | Effect | Annotation |
|---|---|---|
| `provenance_search` | Lexical search of currently readable items, with `source_id` | read-only |
| `provenance_explain` | Versions, readability and dependents of a source; metadata only | read-only |
| `provenance_remember` | Admit one typed item | write |
| `provenance_withdraw` | Withdraw a source and everything derived from it; not physical erasure | destructive |

`--read-only` exposes the first two only; `--no-withdraw` hides the last one.

**Withdrawal notices.** The server records which sources each MCP session was shown. When one is withdrawn, from anywhere, the next tool result of that session carries a `withdrawn_notice` listing the source ids, once per source, with an instruction to stop relying on them.

## Run

```sh
python3 -m pip install . ./packages/hermes-agent-provider ./packages/remote-mcp
umask 077 && python3 -c "import secrets; print(secrets.token_urlsafe(32))" > mcp-token
hermes-memory-mcp --store-dir ./memory-store --create --token-file ./mcp-token
```

The endpoint is `http://127.0.0.1:8766/mcp`. To share the store with Hermes Agent, pass `--store-dir $HERMES_HOME/provenance`.

- The token file must be a regular file readable by its owner only, at least 32 characters long.
- Binding to anything other than loopback requires a token. The server speaks plain HTTP: outside one machine, put it behind TLS (a reverse proxy, or a private overlay network).
- Browser `Origin` headers are refused unless listed with `--allow-origin`, against DNS-rebinding attacks.

## Connect a client

Claude Code:

```sh
claude mcp add --transport http provenance http://127.0.0.1:8766/mcp --header "Authorization: Bearer $(cat mcp-token)"
```

Hermes Agent, in the profile's `config.yaml`:

```yaml
mcp_servers:
  provenance:
    url: http://127.0.0.1:8766/mcp
    headers:
      Authorization: "Bearer <token>"
```

Other clients that take an HTTP MCP URL and custom headers are configured the same way.

## Protocol

- POST `/mcp` carries one JSON-RPC message and is answered with `application/json`. Batches are refused.
- `initialize` opens a session and returns `Mcp-Session-Id`; later requests must send it. DELETE ends a session. GET answers 405: no server-initiated stream is offered.
- Handshake-era versions `2025-11-25`, `2025-06-18` and `2025-03-26` are served; an unknown request version gets `2025-11-25`. A `server/discover` probe from a modern client gets "method not found", which makes it fall back to the handshake.

## Checks

`tests/` starts real servers on ephemeral loopback ports and covers the handshake, sessions, authentication, origins, limits, read-only mode, notices across sessions, and a withdrawal over MCP warning a Hermes Agent provider session on the same store. It is part of `scripts/check_distributions.py`, which installs the core and provider wheels next to it.

Interoperability was observed once, on one Linux host on 14 November 2026. The official MCP Python SDK 2.3.0 client, in its default auto mode, fell back to the handshake at `2025-11-25`, listed the four tools, stored, searched and received a tool error for an unknown source. Hermes Agent at commit `d93e9ba4`, configured with the URL and a bearer header, discovered the four tools and answered a question from the store with its `source_id` values, using a local Qwen3.5-9B.

## Limits

- Bearer tokens only. Clients that require OAuth, such as web connectors, cannot connect yet.
- Sessions live in memory: a restart ends them, and clients reconnect. Notices are tied to MCP sessions, which are not conversations.
- No server-initiated messages: a notice arrives with the session's next tool result.
- Search is lexical. Withdrawal blocks future reads through this library; it cannot recall what a client already copied.

MIT license, see [LICENSE](LICENSE). File provenance is recorded in [PROVENANCE.json](PROVENANCE.json).
