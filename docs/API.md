# Library, CLI and optional service

The local files are separate: authority database, freshness witness, content database, disposable typed index. `Authority.create/open` and `Memory.create/open` are explicit; opening does not adopt a legacy corpus. Core operations are also exposed by `hermes-memory rpc` as JSON requests. Exact refs contain `workspace`, `artifact_id`, `version_id`.

## Local typed CLI

Run from this source distribution with the package installed. Choose an empty local state directory:

```sh
mkdir example-state
hermes-memory --authority example-state/authority.db --anchor example-state/witness.json --store example-state/content.db init
hermes-memory-typed --authority example-state/authority.db --anchor example-state/witness.json --store example-state/content.db --index example-state/index.db --config examples/policy.json put --request examples/source.json
hermes-memory-typed --authority example-state/authority.db --anchor example-state/witness.json --store example-state/content.db --index example-state/index.db --config examples/policy.json sync
hermes-memory-typed --authority example-state/authority.db --anchor example-state/witness.json --store example-state/content.db --index example-state/index.db --config examples/policy.json context --request examples/query.json
```

An identical source retry converges to its existing ref. An update must carry its current `expected_version`; do not derive identity from text alone. `put` does not refresh the search index. `sync` checks configured document/content limits before publication. Query-time automatic sync is absent.

Python API: `TypedMemory.put(workspace, source_id, text, attributes, expected_version=None)`, `sync(workspace, max_documents=5000, max_content_bytes=33554432)`, and `search(workspace, query, as_of=None, conditions=None, evidence_kinds=None, top_k=5, max_context_chars=2000, candidate_limit=100)`.

Metadata admits only `evidence_kind`, `valid_from`, `valid_until`, `observed_at`, `aliases`, `preconditions`, `confidence`. Times use UTC ISO strings ending in `Z`; validity is start-inclusive and end-exclusive. Preconditions require exact supplied values. Past timestamps filter current heads and do not retrieve superseded versions. Confidence is declared metadata, not calibrated probability.

`status=completed` may contain no eligible evidence. Read `context_empty`, `coverage`, `exclusions` and `complete`; completeness is restricted to indexed managed candidates at the current epoch, not the entire historical corpus. `index_stale`, `epoch_changed` and `unavailable` are distinct failure states. A global authority epoch change can stale an otherwise unrelated workspace's index.

## Optional HTTP

Create a token file owned by the service user, mode 0600, at least 32 printable non-space ASCII characters. For an example token without printing it:

```sh
python -c "import os,secrets; p=os.open('example-state/token',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(p,secrets.token_urlsafe(48).encode()); os.close(p)"
hermes-memory-typed --authority example-state/authority.db --anchor example-state/witness.json --store example-state/content.db --index example-state/index.db --config examples/policy.json --host 127.0.0.1 --port 8765 --token-file example-state/token serve
```

Typed routes: `POST /typed/v1/context` and `/typed/v1/status`, bearer authentication, strict JSON schema, 16 KiB requests and 256 KiB responses. Typed admission and sync are local administrative calls, not HTTP routes.

**The combined server also retains the privileged core `/rpc` API.** The same bearer token covers all core operations; there is no per-user or per-workspace authorization. Do not hand this token to an untrusted agent or expose the service as a multi-tenant gateway. The process is a stdlib reference server, not an internet-facing production gateway.

```python
from hermes_memory.typed_client import Client
client = Client("http://127.0.0.1:8765", "example-state/token",
                "typed-pilot-v1", "hermes-typed-pilot-v1")
result = client.context({"query": "copper", "conditions": {"approved": True}})
```

The client disables proxies, redirects and automatic retries, checks exact policy/workspace/refs/coverage/budget, and retains transport-failure provenance. HTTP is limited to numeric loopback or private overlay addresses by the inherited transport contract; use HTTPS outside that boundary. The token loader requires Linux file ownership/link/permission semantics.

`typed_memory_tool.with_tool/execute_tool` is an optional generic function-tool helper. Configuration comes from the application environment, never from model arguments: `HERMES_TYPED_MEMORY_ENABLED=1`, URL, TOKEN_FILE, POLICY and WORKSPACE. Its historical accepted mode names are `hermes` (default) and `legion`; these are selector strings, not connections to a fleet. Cancelled callers do not release a running worker's bounded slot before it exits.

## MCP stdio

`hermes-memory --authority ... --anchor ... --store ... mcp` provides the core stdio session: initialize, tool listing and read/search/explain tools. The transport is local and inherits the launching application's filesystem trust. It does not expose typed HTTP administration or promise a complete remote MCP platform. The shipped core tests exercise actual newline-delimited JSON-RPC exchange.
