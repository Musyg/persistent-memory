# Connect your tools

[Français](SETUP.fr.md) · [MCP server](MCP.md) · [Hermes Agent](HERMES-AGENT.md) · [README](../README.md)

One package, one command per tool. Every tool you connect uses the same store, so something remembered in one is found in the others, and a withdrawal made in one is reported to every tool that was shown the withdrawn entry.

## Install

The package uses the Python standard library only (Python 3.11 or later). Give it its own virtual environment:

```sh
python3 -m venv ~/.persistent-memory
~/.persistent-memory/bin/python -m pip install /path/to/persistent-memory
```

On Windows the commands are in `.persistent-memory\Scripts\`. Until the first PyPI release, install from a checkout or from a release wheel.

If an earlier release is installed under its old name, remove it first: `pip uninstall hermes-memory-core`. Both names contain the same `hermes_memory` module.

## Connect a tool

```sh
~/.persistent-memory/bin/persistent-memory setup claude-code
```

| Client | Scope | What is written |
| --- | --- | --- |
| `claude-code` | `user` (default) | `claude mcp add-json --scope user` |
| | `project` | `.mcp.json` in the project folder |
| `claude-desktop` | `user` | `claude_desktop_config.json` (macOS `~/Library/Application Support/Claude`, Windows `%APPDATA%\Claude` or the Microsoft Store folder, Linux `~/.config/Claude`) |
| `cursor` | `user` / `project` | `~/.cursor/mcp.json` / `.cursor/mcp.json` |
| `vscode` (GitHub Copilot) | `user` / `project` | `~/.copilot/mcp-config.json` (or `$COPILOT_HOME`) / `.mcp.json` |
| `windsurf` | `user` | `~/.codeium/windsurf/mcp_config.json` |
| `codex` | `user` | `~/.codex/config.toml` (or `$CODEX_HOME`), table `[mcp_servers.persistent-memory]` |
| `hermes-agent` | `user` | Hermes Agent's memory provider, or an MCP server; see below |

`claude`, `copilot` and `hermes` are accepted as short names. A project `.mcp.json` is read by both Claude Code and Copilot.

Each entry starts `python -m hermes_memory.mcp_server` with the absolute path of this environment's Python, so the tool does not depend on `PATH`. The [MCP server](MCP.md) page describes the ten tools.

## One store, shared

`setup` creates the store once, then every tool opens it. Default location:

| System | Store |
| --- | --- |
| Linux | `$XDG_DATA_HOME/persistent-memory`, else `~/.local/share/persistent-memory` |
| macOS | `~/Library/Application Support/persistent-memory` |
| Windows | `%LOCALAPPDATA%\persistent-memory` |

`$PERSISTENT_MEMORY_DIR` or `--store` chooses another one. Tools with the same store and the same `--workspace` (default `default`) share their memory; give a tool another workspace to keep it apart. The configured server does not create a missing store: if the folder disappears, the tool reports it instead of starting from an empty memory.

## Options

| Option | Meaning |
| --- | --- |
| `--scope user\|project` | Every project, or one project's file to commit or share. |
| `--project-dir DIR` | Project folder for `--scope project`. Default: the current folder. |
| `--store DIR`, `--workspace NAME` | Where the memory lives and which part of it this tool uses. |
| `--name NAME` | Server name in the tool. Default `persistent-memory`. |
| `--dry-run` | Show what would change. Nothing is written and no store is created. |
| `--remove` | Remove the entry. The store is left untouched. |
| `--force` | Replace or remove an entry of the same name that runs another server. |
| `--json` | Print the result as JSON. |

`persistent-memory status` shows the default store and which configuration files already run this memory. `persistent-memory mcp` runs the server itself with the same options as `persistent-memory-mcp`.

## What setup will and will not do

- Other servers and settings in a file are kept as they are.
- A file it cannot parse, such as JSON with comments, is not touched; the entry to add by hand is printed.
- An entry with the same name that runs something else is not replaced without `--force`. Choose another `--name` to keep both.
- Before changing an existing file it saves a copy next to it, `<file>.persistent-memory-<time>.bak`, then writes the new content to a temporary file and renames it into place. A symbolic link is followed to its target.
- Running the same command again changes nothing.
- For Codex, the result is parsed again before writing; if anything besides this entry would change, nothing is written.
- Claude Code's user configuration and Hermes Agent's configuration are changed through their own command lines, never by editing their files.

## Hermes Agent

Install the package in Hermes Agent's own environment and run `persistent-memory setup hermes-agent` from there. It selects the [memory provider](HERMES-AGENT.md) with `hermes config set memory.provider persistent-memory` and writes the store and workspace into `$HERMES_HOME/persistent-memory/config.json`, keeping the other settings. Hermes Agent then recalls validated memory before each turn and opens a turn with a notice when something it was shown is withdrawn.

Hermes Agent accepts one external memory provider. If another one is selected, setup stops; `--force` replaces it, `--hermes-mode mcp` adds the MCP server instead. When the package is not in Hermes Agent's environment, setup uses the MCP mode by itself: `hermes config set mcp_servers.persistent-memory ...`, and the tools appear in the `mcp-persistent-memory` toolset. `--hermes-command` gives the path of `hermes` when it is not found.

## Observed

On 14 November 2026, on Linux, in a new virtual environment with Python 3.12 and the package installed from its wheel, each tool using a temporary configuration folder:

- Claude Code 2.1.289: `setup claude-code` registered the server through `claude mcp add-json`; a second run reported it unchanged; `claude mcp list` showed it connected.
- Codex CLI 0.166.0: `codex mcp list` and `codex mcp get` read the entry that `setup codex` wrote.
- Hermes Agent: `hermes memory status` showed `persistent-memory` active and available. With a local 9B model, Hermes Agent stored a fact with `memory_remember`; the server configured for Claude Code and Codex found it with `memory_search`.

On 15 November 2026:

- Linux, Claude Code with a model turn, from a project `.mcp.json` written by `setup claude-code --scope project`: Claude stored a fact with `memory_remember`; in a new session it found it with `memory_search` and cited its `artifact_id`; after the fact was withdrawn from outside, the next session found nothing and said so.
- Windows 10, Python 3.13, in a temporary profile folder: `setup` wrote the Claude Desktop, Cursor, VS Code (project) and Windsurf files; a second run reported them unchanged; `status` listed them.

Claude Desktop, Cursor, VS Code and Windsurf files follow each tool's current documentation; they were written and checked by tests, not opened in those applications.

## Tests

`tests/test_client_setup.py` covers each client's file or command, the default store on each system, refusals (foreign entry, unparsable file, unsupported scope), backups, file permissions, symbolic links, idempotence, removal, dry runs, quoting in TOML, and an end-to-end start of the configured command speaking MCP. The `claude` and `hermes` commands are replaced by stand-ins in these tests.
