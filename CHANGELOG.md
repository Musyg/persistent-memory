# Changelog

All notable changes to `persistent-memory` are recorded here. The project is an alpha library: versions use PEP 440 pre-release numbers (`0.4.0a2`) and interfaces can still change between pre-releases.

## Unreleased

### Fixed

- HTTP servers (core `/rpc` and `/validate`, typed routes, MCP over Streamable HTTP): a refused request (401, 403, 404, 405) now has its body read before the answer is sent. Before, the server closed the connection with unread data, and the client could get a reset connection instead of the answer; this was seen once on Windows in CI. The tests that send refused requests now send 40 of them with a body of 1 to 2 MB.

## 0.4.0a2 (2026-11-15)

First release on PyPI, as `persistent-memory-mcp` (`0.4.0a1` is skipped: that tag is an earlier public pre-release, see PACKAGES.md) (module `hermes_memory`, unchanged). Releases up to 0.3.0a5 were published as `hermes-memory-core`; see [Earlier releases](#earlier-releases). Uninstall `hermes-memory-core` before installing `persistent-memory-mcp`: both contain the `hermes_memory` module.

### Added

- Any agent framework: [docs/FRAMEWORKS.md](docs/FRAMEWORKS.md) lists the frameworks whose MCP integration was checked, with a snippet for each. An optional MCP argument sent as `null` now counts as absent.
- Public import name `persistent_memory` (`from persistent_memory import PersistentMemory`). It exposes the same objects as `hermes_memory`, which remains importable.
- Rename of the distribution to `persistent-memory-mcp` (`persistent-memory` is refused by PyPI as too close to an existing project). Console scripts: `persistent-memory` and `persistent-memory-mcp`, next to the existing `hermes-memory`, `hermes-memory-typed` and `hermes-memory-demo`.
- Operations surface: `hermes_memory.persistent.PersistentMemory` gathers sources, derived artifacts with exact parents, corrections, withdrawal with cascade, lessons and withdrawal notices behind one class ([docs/OPERATIONS.md](docs/OPERATIONS.md)).
- MCP server over stdio and over HTTP ([docs/MCP.md](docs/MCP.md)).
- Hermes Agent memory provider, registered through the `hermes_agent.memory_providers` entry point ([docs/HERMES-AGENT.md](docs/HERMES-AGENT.md)).
- Qdrant projection, an optional search projection rebuilt from the authority ([docs/QDRANT.md](docs/QDRANT.md)).
- `persistent-memory setup` and `persistent-memory status`: one command per tool to connect it to the same store ([docs/SETUP.md](docs/SETUP.md)).
- Linux, macOS and Windows are qualified. The installed-package tests run on the three systems in CI, Python 3.11 to 3.14, with an FTS5 preflight.
- Release workflow using PyPI Trusted Publishing, with a TestPyPI gate and a manual approval before PyPI ([docs/RELEASING.md](docs/RELEASING.md)).

### Changed

- Core revision for Windows, approved by the owner: every SQLite connection is closed when its block ends, the anchor is written without a directory sync on Windows, and its replacement is retried briefly when another process holds it open.
- Typed wire change: the core hash pinned by the typed layer changes with that revision, so a 0.3 typed client and a 0.4 typed server refuse each other. Upgrade both together.
- A half-created store is refused (`store_incomplete`); startup errors print one line and exit with status 2.
- The MCP stdio server reads and writes binary streams, and the command-line tools write UTF-8 bytes to pipes.
- Package metadata: SPDX license expression (`MIT`, PEP 639, needs setuptools 77 or later to build), author, project URLs and classifiers.

### Notes

- The optional policy registry (`hermes-policy-registry`, 0.2.0a2) is a separate distribution. It is not published to PyPI and has no runtime dependency on this package.

## Earlier releases

Versions 0.3.0a5 and earlier were published as `hermes-memory-core` on GitHub. Their release notes, archives and checksums are linked from [PACKAGES.md](PACKAGES.md); the 0.3.0a5 qualification receipt is in [docs/releases/0.3.0a5](docs/releases/0.3.0a5/README.md). Git tags `v0.2.0a1` to `v0.3.0a5` mark them.
