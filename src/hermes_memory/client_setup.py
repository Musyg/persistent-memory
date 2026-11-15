"""Connect MCP clients and Hermes Agent to one persistent memory store.

``persistent-memory setup <client>`` writes the client's own configuration so that it starts
``python -m hermes_memory.mcp_server`` from this environment, against one shared store. Rules:

- other entries and keys in a configuration file are kept as they are;
- a file that cannot be parsed is never touched; the entry to add by hand is printed instead;
- an existing entry of the same name that does not run this server is never replaced without
  ``--force``;
- an existing file is copied to ``<file>.persistent-memory-<time>.bak`` before it is changed, and
  the new content is written to a temporary file and renamed into place;
- running the same command twice changes nothing the second time.

Clients that own their configuration through a command line (Claude Code at user scope, Hermes
Agent) are configured through that command line rather than by editing their files.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .core import MemoryError, name as valid_identifier

SERVER_MODULE = "hermes_memory.mcp_server"
DEFAULT_NAME = "persistent-memory"
DEFAULT_WORKSPACE = "default"
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
HERMES_PROVIDER = "persistent-memory"


class SetupError(Exception):
    """A configuration could not be changed safely. Nothing was written."""


@dataclass
class Context:
    """Everything setup reads from the machine, so tests can replace it."""
    home: Path
    cwd: Path
    env: dict
    platform: str
    python: str
    run: object = None
    which: object = None
    now: object = None

    @classmethod
    def current(cls):
        return cls(home=Path.home(), cwd=Path.cwd(), env=dict(os.environ), platform=sys.platform,
                   python=sys.executable, run=_run, which=shutil.which,
                   now=lambda: time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))

    @property
    def windows(self):
        return self.platform.startswith("win")


def _run(argv):
    return subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=120)


@dataclass
class Result:
    client: str
    scope: str
    action: str                      # added, updated, unchanged, removed, absent, set
    target: str                      # file or command that holds the configuration
    backup: str | None = None
    commands: list = field(default_factory=list)
    notes: list = field(default_factory=list)


# -- store and server command ------------------------------------------------------------------

def default_store(env=None, platform=None, home=None):
    """The store every client shares unless told otherwise."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else Path(home)
    if env.get("PERSISTENT_MEMORY_DIR"):
        return Path(os.path.expanduser(env["PERSISTENT_MEMORY_DIR"]))
    if platform.startswith("win"):
        base = Path(env["LOCALAPPDATA"]) if env.get("LOCALAPPDATA") else home / "AppData" / "Local"
    elif platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        xdg = env.get("XDG_DATA_HOME", "")
        base = Path(xdg) if xdg and os.path.isabs(xdg) else home / ".local" / "share"
    return base / "persistent-memory"


def server_args(store, workspace):
    return ["-m", SERVER_MODULE, "--store", str(store), "--workspace", workspace]


def is_ours(entry):
    """True when a client entry starts this server, whichever way it was written."""
    if not isinstance(entry, dict):
        return False
    args = entry.get("args") or []
    if not isinstance(args, list):
        return False
    args = [str(a) for a in args]
    program = re.split(r"[\\/]", str(entry.get("command", "")))[-1].lower()
    program = program[:-4] if program.endswith(".exe") else program
    return (SERVER_MODULE in args or program == "persistent-memory-mcp"
            or (program == "persistent-memory" and args[:1] == ["mcp"]))


def same_server(existing, entry):
    return (isinstance(existing, dict) and existing.get("command") == entry["command"]
            and existing.get("args") == entry["args"])


# -- JSON files --------------------------------------------------------------------------------

def _read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise SetupError("cannot read %s: %s" % (path, exc)) from None


def snippet(key, name, entry):
    return json.dumps({key: {name: entry}}, indent=2, ensure_ascii=False)


def plan_json(path, key, name, entry, *, remove=False, force=False):
    """Return (action, new_text or None) for one server entry under ``key`` in a JSON file."""
    text = _read_text(path)
    hint = "\nAdd this by hand:\n" + snippet(key, name, entry) if not remove else ""
    if text is None or not text.strip():
        data = {}
    else:
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise SetupError("%s is not plain JSON (%s); nothing changed.%s" % (path, exc, hint)) from None
    if not isinstance(data, dict) or not isinstance(data.get(key, {}), dict):
        raise SetupError("%s does not have the expected shape; nothing changed.%s" % (path, hint))
    servers = data.get(key, {})
    existing = servers.get(name)
    if remove:
        if existing is None:
            return "absent", None
        if not is_ours(existing) and not force:
            raise SetupError("%s: the entry %r does not run persistent-memory; use --force to remove it"
                             % (path, name))
        del servers[name]
        return "removed", json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if same_server(existing, entry):
        return "unchanged", None
    if existing is not None and not is_ours(existing) and not force:
        raise SetupError("%s: an entry named %r already exists and does not run persistent-memory; "
                         "choose another --name or use --force" % (path, name))
    data[key] = servers
    servers[name] = entry
    return ("updated" if existing is not None else "added"), json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_file(path, text, ctx):
    """Back up, then replace ``path`` atomically. Symlinks are followed to their target."""
    path = Path(os.path.realpath(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    backup, mode = None, None
    if path.exists():
        stamp = ctx.now()
        backup = path.with_name("%s.persistent-memory-%s.bak" % (path.name, stamp))
        counter = 1
        while backup.exists():
            counter += 1
            backup = path.with_name("%s.persistent-memory-%s-%d.bak" % (path.name, stamp, counter))
        shutil.copy2(path, backup)
        mode = path.stat().st_mode & 0o777
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return str(backup) if backup else None


# -- TOML (Codex) ------------------------------------------------------------------------------

def toml_string(value):
    out = []
    for ch in str(value):
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def toml_block(name, entry):
    args = ", ".join(toml_string(a) for a in entry["args"])
    return "[mcp_servers.%s]\ncommand = %s\nargs = [%s]\n" % (name, toml_string(entry["command"]), args)


def _without(data, name):
    """The parsed document without this entry, an empty mcp_servers table counting as absent."""
    copy = dict(data)
    servers = dict(copy.pop("mcp_servers", {}))
    servers.pop(name, None)
    if servers:
        copy["mcp_servers"] = servers
    return copy


def _strip_table(text, name):
    header = re.compile(r'^\s*\[\s*mcp_servers\s*\.\s*(?:%s|"%s")\s*(?:\.[^\]]*)?\]\s*(?:#.*)?$'
                        % (re.escape(name), re.escape(name)))
    any_header = re.compile(r"^\s*\[")
    kept, skipping = [], False
    for line in text.splitlines(keepends=True):
        if header.match(line):
            skipping = True
            continue
        if skipping and any_header.match(line):
            skipping = False
        if not skipping:
            kept.append(line)
    return "".join(kept)


def plan_toml(path, name, entry, *, remove=False, force=False):
    text = _read_text(path) or ""
    hint = "\nAdd this by hand:\n" + toml_block(name, entry) if not remove else ""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise SetupError("%s is not valid TOML (%s); nothing changed.%s" % (path, exc, hint)) from None
    servers = data.get("mcp_servers", {})
    if not isinstance(servers, dict):
        raise SetupError("%s: mcp_servers is not a table; nothing changed.%s" % (path, hint))
    existing = servers.get(name)
    if remove and existing is None:
        return "absent", None
    if not remove and same_server(existing, entry):
        return "unchanged", None
    if existing is not None and not is_ours(existing) and not force:
        raise SetupError("%s: an entry named %r already exists and does not run persistent-memory; "
                         "choose another --name or use --force" % (path, name))
    new_text = _strip_table(text, name) if existing is not None else text
    if not remove:
        new_text = new_text.rstrip("\n")
        new_text = (new_text + "\n\n" if new_text else "") + toml_block(name, entry)
    try:
        parsed = tomllib.loads(new_text)
    except tomllib.TOMLDecodeError:
        parsed = None
    expected = None if remove else {"command": entry["command"], "args": entry["args"]}
    if (parsed is None or parsed.get("mcp_servers", {}).get(name) != expected
            or _without(parsed, name) != _without(data, name)):
        raise SetupError("%s: the entry %r is written in a form this tool does not edit; "
                         "nothing changed.%s" % (path, name, hint))
    return ("removed" if remove else "updated" if existing is not None else "added"), new_text


# -- clients -----------------------------------------------------------------------------------

def claude_desktop_config(ctx):
    if ctx.windows:
        appdata = Path(ctx.env["APPDATA"]) if ctx.env.get("APPDATA") else ctx.home / "AppData" / "Roaming"
        standard = appdata / "Claude" / "claude_desktop_config.json"
        local = Path(ctx.env["LOCALAPPDATA"]) if ctx.env.get("LOCALAPPDATA") else ctx.home / "AppData" / "Local"
        # The Microsoft Store build keeps its configuration in a virtualised folder.
        packaged = sorted((local / "Packages").glob("Claude_*/LocalCache/Roaming/Claude")) \
            if (local / "Packages").is_dir() else []
        if packaged and not standard.parent.exists():
            return packaged[0] / "claude_desktop_config.json"
        return standard
    if ctx.platform == "darwin":
        return ctx.home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    xdg = ctx.env.get("XDG_CONFIG_HOME", "")
    base = Path(xdg) if xdg and os.path.isabs(xdg) else ctx.home / ".config"
    return base / "Claude" / "claude_desktop_config.json"


def claude_user_file(ctx):
    base = Path(ctx.env["CLAUDE_CONFIG_DIR"]) if ctx.env.get("CLAUDE_CONFIG_DIR") else ctx.home
    return base / ".claude.json"


def copilot_home(ctx):
    return Path(ctx.env["COPILOT_HOME"]) if ctx.env.get("COPILOT_HOME") else ctx.home / ".copilot"


def codex_config(ctx):
    base = Path(ctx.env["CODEX_HOME"]) if ctx.env.get("CODEX_HOME") else ctx.home / ".codex"
    return base / "config.toml"


# client -> {scope: (path function, key, extra entry fields)} for clients configured by file.
FILE_CLIENTS = {
    "claude-code": {"project": (lambda c, p: p / ".mcp.json", "mcpServers", {"type": "stdio"})},
    "claude-desktop": {"user": (lambda c, p: claude_desktop_config(c), "mcpServers", {})},
    "cursor": {"user": (lambda c, p: c.home / ".cursor" / "mcp.json", "mcpServers", {"type": "stdio"}),
               "project": (lambda c, p: p / ".cursor" / "mcp.json", "mcpServers", {"type": "stdio"})},
    "vscode": {"user": (lambda c, p: copilot_home(c) / "mcp-config.json", "mcpServers",
                        {"type": "stdio", "tools": ["*"]}),
               "project": (lambda c, p: p / ".mcp.json", "mcpServers", {"type": "stdio"})},
    "windsurf": {"user": (lambda c, p: c.home / ".codeium" / "windsurf" / "mcp_config.json", "mcpServers", {})},
}
CLIENTS = {
    "claude-code": ("user", "project"),
    "claude-desktop": ("user",),
    "cursor": ("user", "project"),
    "vscode": ("user", "project"),
    "windsurf": ("user",),
    "codex": ("user",),
    "hermes-agent": ("user",),
}
ALIASES = {"claude": "claude-code", "copilot": "vscode", "hermes": "hermes-agent"}
NEXT_STEP = {
    "claude-code": "Start Claude Code; /mcp lists the server. A project .mcp.json asks for approval once.",
    "claude-desktop": "Quit and reopen Claude Desktop.",
    "cursor": "Open Cursor Settings > MCP and check that the server is enabled.",
    "vscode": "Open a Copilot chat in agent mode; the server's tools appear in the tools list.",
    "windsurf": "Refresh the MCP servers in Cascade, or restart Windsurf.",
    "codex": "Start Codex; /mcp lists the server.",
    "hermes-agent": "Start a new Hermes Agent session (restart the gateway if one is running).",
}


@dataclass
class Request:
    client: str
    scope: str | None = None
    store: str | None = None
    workspace: str = DEFAULT_WORKSPACE
    name: str = DEFAULT_NAME
    project_dir: str | None = None
    remove: bool = False
    force: bool = False
    dry_run: bool = False
    hermes_mode: str = "auto"
    hermes_command: str | None = None


def resolve(request, ctx):
    client = ALIASES.get(request.client, request.client)
    if client not in CLIENTS:
        raise SetupError("unknown client %r; choose one of: %s" % (request.client, ", ".join(CLIENTS)))
    scope = request.scope or CLIENTS[client][0]
    if scope not in CLIENTS[client]:
        raise SetupError("%s supports --scope %s only" % (client, " or ".join(CLIENTS[client])))
    if not NAME_PATTERN.match(request.name):
        raise SetupError("--name must be 1 to 64 letters, digits, '-' or '_'")
    try:
        valid_identifier(request.workspace)
    except MemoryError:
        raise SetupError("invalid --workspace") from None
    store = Path(os.path.expanduser(request.store)) if request.store else \
        default_store(ctx.env, ctx.platform, ctx.home)
    if not store.is_absolute():
        store = ctx.cwd / store
    project = Path(request.project_dir) if request.project_dir else ctx.cwd
    if not project.is_absolute():
        project = ctx.cwd / project
    return client, scope, store, project


def setup(request, ctx=None):
    """Configure one client. Returns a Result; raises SetupError without writing anything."""
    ctx = ctx or Context.current()
    client, scope, store, project = resolve(request, ctx)
    entry = {"command": ctx.python, "args": server_args(store, request.workspace)}
    if client == "hermes-agent":
        result = _hermes(request, ctx, store, entry)
    elif client == "codex":
        path = codex_config(ctx)
        action, text = plan_toml(path, request.name, entry, remove=request.remove, force=request.force)
        result = _apply(client, scope, path, action, text, request, ctx)
    elif client == "claude-code" and scope == "user":
        result = _claude_user(request, ctx, entry)
    else:
        path_of, key, extra = FILE_CLIENTS[client][scope]
        path = path_of(ctx, project)
        full = {**({"type": extra["type"]} if "type" in extra else {}), **entry,
                **{k: v for k, v in extra.items() if k != "type"}}
        action, text = plan_json(path, key, request.name, full, remove=request.remove, force=request.force)
        result = _apply(client, scope, path, action, text, request, ctx)
    result.client, result.scope = client, scope
    if not request.remove and result.action != "absent":
        if not request.dry_run:
            _ensure_store(store, request.workspace)
        result.notes.insert(0, "store: %s (workspace %s)" % (store, request.workspace))
        result.notes.append(NEXT_STEP[client])
    return result


def _ensure_store(store, workspace):
    from .persistent import PersistentMemory
    try:
        PersistentMemory(store, workspace, create=True)
    except MemoryError as exc:
        raise SetupError("cannot open or create the store at %s: %s" % (store, exc)) from None


def _apply(client, scope, path, action, text, request, ctx):
    result = Result(client, scope, action, str(path))
    if text is not None and not request.dry_run:
        result.backup = write_file(path, text, ctx)
    if text is not None and request.dry_run:
        result.notes.append("dry run: %s would be written" % path)
    return result


def _check(completed, what):
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip().splitlines()
        raise SetupError("%s failed: %s" % (what, message[-1] if message else "exit %d" % completed.returncode))
    return completed


def _claude_user(request, ctx, entry):
    path = claude_user_file(ctx)
    claude = ctx.which("claude")
    entry = {"type": "stdio", **entry}
    add = ["claude", "mcp", "add-json", "--scope", "user", request.name, json.dumps(entry)]
    drop = ["claude", "mcp", "remove", "--scope", "user", request.name]
    try:
        text = _read_text(path)
        existing = (json.loads(text).get("mcpServers") or {}).get(request.name) if text else None
        known = True
    except (SetupError, ValueError, AttributeError):
        existing, known = None, False
    if request.remove:
        if known and existing is None:
            return Result("claude-code", "user", "absent", str(path))
        if existing is not None and not is_ours(existing) and not request.force:
            raise SetupError("Claude Code's user entry %r does not run persistent-memory; use --force to remove it"
                             % request.name)
        steps, action = [drop], "removed"
    else:
        if same_server(existing, entry):
            return Result("claude-code", "user", "unchanged", str(path))
        if existing is not None and not is_ours(existing) and not request.force:
            raise SetupError("Claude Code already has a user entry named %r that does not run persistent-memory; "
                             "choose another --name or use --force" % request.name)
        steps, action = ([drop, add] if existing is not None else [add]), \
            ("updated" if existing is not None else "added")
    result = Result("claude-code", "user", action, "claude mcp (user scope)",
                    commands=[" ".join(_quote(a) for a in s) for s in steps])
    if request.dry_run:
        result.notes.append("dry run: the commands above would run")
        return result
    if claude is None:
        raise SetupError("the claude command was not found. Use --scope project, or run:\n  "
                         + "\n  ".join(result.commands))
    for step in steps:
        _check(ctx.run([claude] + step[1:]), " ".join(step[:3]))
    return result


def _quote(arg):
    return arg if re.match(r"^[A-Za-z0-9_./:=@+-]+$", arg) else "'" + arg.replace("'", "'\"'\"'") + "'"


def _hermes_command(request, ctx):
    if request.hermes_command:
        return request.hermes_command, True
    local = Path(ctx.python).parent / ("hermes.exe" if ctx.windows else "hermes")
    if local.is_file():
        return str(local), True
    found = ctx.which("hermes")
    return found, False


def _hermes(request, ctx, store, entry):
    hermes, same_env = _hermes_command(request, ctx)
    mode = request.hermes_mode
    if mode == "auto":
        mode = "provider" if same_env else "mcp"
    if hermes is None:
        raise SetupError("Hermes Agent's hermes command was not found. Install persistent-memory in Hermes "
                         "Agent's environment and run this from there, or pass --hermes-command")
    if mode == "provider" and not same_env:
        raise SetupError("the memory provider must be installed in Hermes Agent's own environment: install "
                         "persistent-memory there and run its persistent-memory setup hermes-agent, "
                         "or use --hermes-mode mcp")
    run = lambda *args: ctx.run([hermes, "config"] + list(args))
    if mode == "provider":
        return _hermes_provider(request, ctx, run, store)
    return _hermes_mcp(request, ctx, run, entry)


def _hermes_provider(request, ctx, run, store):
    config_file = _check(run("path"), "hermes config path").stdout.strip().splitlines()[-1].strip()
    provider_file = Path(config_file).parent / HERMES_PROVIDER / "config.json"
    current = run("get", "memory.provider")
    current = current.stdout.strip() if current.returncode == 0 else ""
    if request.remove:
        if current != HERMES_PROVIDER:
            return Result("hermes-agent", "user", "absent", config_file)
        result = Result("hermes-agent", "user", "removed", config_file,
                        commands=["hermes config unset memory.provider"],
                        notes=["%s is kept; it holds no secret" % provider_file])
        if not request.dry_run:
            _check(run("unset", "memory.provider"), "hermes config unset")
        return result
    if current and current != HERMES_PROVIDER and not request.force:
        raise SetupError("Hermes Agent already uses the memory provider %r and accepts only one; use --force "
                         "to replace it, or --hermes-mode mcp to add the MCP server instead" % current)
    text = _read_text(provider_file)
    try:
        settings = json.loads(text) if text and text.strip() else {}
    except ValueError:
        raise SetupError("%s is not valid JSON; nothing changed" % provider_file) from None
    if not isinstance(settings, dict):
        raise SetupError("%s does not hold a JSON object; nothing changed" % provider_file)
    wanted = {"store_dir": str(store), "workspace": request.workspace}
    changed_settings = any(settings.get(k) != v for k, v in wanted.items())
    if not changed_settings and current == HERMES_PROVIDER:
        return Result("hermes-agent", "user", "unchanged", config_file)
    result = Result("hermes-agent", "user", "updated" if current == HERMES_PROVIDER else "added", config_file)
    if current != HERMES_PROVIDER:
        result.commands.append("hermes config set memory.provider " + HERMES_PROVIDER)
    if request.dry_run:
        result.notes.append("dry run: %s and the commands above would be written" % provider_file)
        return result
    if changed_settings:
        result.backup = write_file(provider_file, json.dumps({**settings, **wanted}, indent=2) + "\n", ctx)
    if current != HERMES_PROVIDER:
        _check(run("set", "memory.provider", HERMES_PROVIDER), "hermes config set")
    result.notes.append("provider settings: %s" % provider_file)
    return result


def _hermes_mcp(request, ctx, run, entry):
    key = "mcp_servers." + request.name
    args = run("get", key + ".args")
    exists = args.returncode == 0
    ours = exists and SERVER_MODULE in args.stdout
    if exists and not ours and not request.force:
        raise SetupError("Hermes Agent already has an MCP server named %r that does not run persistent-memory; "
                         "choose another --name or use --force" % request.name)
    if request.remove:
        if not exists:
            return Result("hermes-agent", "user", "absent", "hermes config " + key)
        result = Result("hermes-agent", "user", "removed", "hermes config " + key,
                        commands=["hermes config unset " + key])
        if not request.dry_run:
            _check(run("unset", key), "hermes config unset")
        return result
    value = json.dumps({**entry, "timeout": 60})
    result = Result("hermes-agent", "user", "updated" if exists else "added", "hermes config " + key,
                    commands=["hermes config set %s %s" % (key, _quote(value))],
                    notes=["the tools appear in the mcp-%s toolset" % request.name])
    if not request.dry_run:
        _check(run("set", key, value), "hermes config set")
    return result


# -- status ------------------------------------------------------------------------------------

def status(ctx=None, project_dir=None, name=DEFAULT_NAME):
    """Read-only view: which client files hold an entry that runs this server."""
    ctx = ctx or Context.current()
    project = Path(project_dir) if project_dir else ctx.cwd
    rows = []
    for client, scopes in FILE_CLIENTS.items():
        for scope, (path_of, key, _) in scopes.items():
            rows.append((client, scope, path_of(ctx, project), key))
    rows.append(("claude-code", "user", claude_user_file(ctx), "mcpServers"))
    rows.append(("codex", "user", codex_config(ctx), "mcp_servers"))
    report = []
    for client, scope, path, key in rows:
        try:
            text = _read_text(path)
        except SetupError:
            text, state = None, "unreadable"
        else:
            state = "no file" if text is None else "not configured"
        if text:
            try:
                data = tomllib.loads(text) if path.suffix == ".toml" else json.loads(text)
                found = [n for n, e in (data.get(key) or {}).items() if is_ours(e)]
                state = "configured as " + ", ".join(found) if found else state
            except (ValueError, AttributeError, tomllib.TOMLDecodeError):
                state = "cannot parse"
        report.append({"client": client, "scope": scope, "file": str(path), "state": state})
    return report
