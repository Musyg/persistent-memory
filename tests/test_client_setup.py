"""persistent-memory setup: client configuration files, shared store, refusals and round trips."""
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hermes_memory import client_setup as cs
from hermes_memory import persistent_cli
from hermes_memory.client_setup import Context, Request, SetupError, setup


def done(code=0, out="", err=""):
    return SimpleNamespace(returncode=code, stdout=out, stderr=err)


class FakeTools:
    """Stand-ins for the claude and hermes command lines."""

    def __init__(self, root):
        self.calls = []
        self.claude_file = root / "home" / ".claude.json"
        self.hermes_config = {}
        self.hermes_path = root / "hermes-home" / "config.yaml"

    def run(self, argv):
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        program = Path(argv[0]).name
        if program == "claude":
            data = json.loads(self.claude_file.read_text()) if self.claude_file.exists() else {}
            servers = data.setdefault("mcpServers", {})
            if argv[1:3] == ["mcp", "add-json"]:
                if argv[5] in servers:
                    return done(1, err="MCP server %s already exists in user config" % argv[5])
                servers[argv[5]] = {**json.loads(argv[6]), "env": {}}
            elif argv[1:3] == ["mcp", "remove"]:
                if servers.pop(argv[5], None) is None:
                    return done(1, err="No MCP server found")
            self.claude_file.parent.mkdir(parents=True, exist_ok=True)
            self.claude_file.write_text(json.dumps(data))
            return done()
        if program == "hermes":
            verb = argv[2]
            if verb == "path":
                return done(out=str(self.hermes_path) + "\n")
            node = self.hermes_config
            keys = argv[3].split(".") if len(argv) > 3 else []
            if verb == "get":
                for key in keys:
                    if not isinstance(node, dict) or key not in node:
                        return done(1, out="Config key not set: %s\n" % argv[3])
                    node = node[key]
                return done(out=(node if isinstance(node, str) else json.dumps(node)) + "\n")
            for key in keys[:-1]:
                node = node.setdefault(key, {})
            if verb == "set":
                value = argv[4]
                node[keys[-1]] = json.loads(value) if value[:1] in "{[" else value
            elif verb == "unset":
                node.pop(keys[-1], None)
            return done(out="ok\n")
        raise AssertionError(argv)


class SetupCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.project = self.root / "project"
        self.home.mkdir()
        self.project.mkdir()
        self.tools = FakeTools(self.root)
        self.on_path = {"claude": "/usr/local/bin/claude"}
        self.ctx = Context(home=self.home, cwd=self.project, env={}, platform="linux", python=sys.executable,
                           run=self.tools.run, which=lambda n: self.on_path.get(n),
                           now=lambda: "20261114T120000Z")
        self.store = self.root / "store"

    def tearDown(self):
        self.tmp.cleanup()

    def setup(self, client, **kw):
        kw.setdefault("store", str(self.store))
        return setup(Request(client=client, **kw), self.ctx)

    def entry(self, **extra):
        return {**extra, "command": sys.executable,
                "args": ["-m", "hermes_memory.mcp_server", "--store", str(self.store), "--workspace", "default"]}


class DefaultStoreTest(unittest.TestCase):
    def test_platform_folders(self):
        home = Path("/h")
        self.assertEqual(cs.default_store({}, "linux", home), home / ".local/share/persistent-memory")
        self.assertEqual(cs.default_store({"XDG_DATA_HOME": "/x"}, "linux", home), Path("/x/persistent-memory"))
        self.assertEqual(cs.default_store({"XDG_DATA_HOME": "rel"}, "linux", home),
                         home / ".local/share/persistent-memory")
        self.assertEqual(cs.default_store({}, "darwin", home),
                         home / "Library/Application Support/persistent-memory")
        self.assertEqual(cs.default_store({"LOCALAPPDATA": "/L"}, "win32", home), Path("/L/persistent-memory"))
        self.assertEqual(cs.default_store({}, "win32", home), home / "AppData/Local/persistent-memory")
        self.assertEqual(cs.default_store({"PERSISTENT_MEMORY_DIR": "/s", "XDG_DATA_HOME": "/x"}, "linux", home),
                         Path("/s"))

    def test_server_uses_default_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "XDG_DATA_HOME": tmp, "PERSISTENT_MEMORY_DIR": ""}
            env.pop("PERSISTENT_MEMORY_DIR")
            proc = subprocess.run([sys.executable, "-m", "hermes_memory.mcp_server"], input=b"", env=env,
                                  capture_output=True, timeout=60)
            self.assertEqual(proc.returncode, 2)
            self.assertIn(b"store_missing", proc.stderr)
            proc = subprocess.run([sys.executable, "-m", "hermes_memory.mcp_server", "--create"], input=b"",
                                  env=env, capture_output=True, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((Path(tmp) / "persistent-memory" / "authority" / "authority.db").exists())


class JsonClientsTest(SetupCase):
    def test_add_creates_file_and_store_then_is_idempotent(self):
        result = self.setup("cursor")
        path = self.home / ".cursor" / "mcp.json"
        self.assertEqual((result.action, result.target, result.backup), ("added", str(path), None))
        self.assertEqual(json.loads(path.read_text()), {"mcpServers": {"persistent-memory": self.entry(type="stdio")}})
        self.assertTrue((self.store / "authority" / "authority.db").exists())
        before = path.read_bytes()
        again = self.setup("cursor")
        self.assertEqual((again.action, again.backup), ("unchanged", None))
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["mcp.json"])

    def test_keeps_other_entries_backs_up_and_keeps_mode(self):
        path = self.home / ".codeium" / "windsurf" / "mcp_config.json"
        path.parent.mkdir(parents=True)
        original = {"theme": "dark", "mcpServers": {"other": {"command": "npx", "args": ["x"]}}}
        path.write_text(json.dumps(original))
        os.chmod(path, 0o640)
        result = self.setup("windsurf")
        data = json.loads(path.read_text())
        self.assertEqual(data["theme"], "dark")
        self.assertEqual(data["mcpServers"]["other"], original["mcpServers"]["other"])
        self.assertEqual(data["mcpServers"]["persistent-memory"], self.entry())
        self.assertEqual(json.loads(Path(result.backup).read_text()), original)
        self.assertTrue(result.backup.endswith("mcp_config.json.persistent-memory-20261114T120000Z.bak"))
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
        second = self.setup("windsurf", store=str(self.root / "elsewhere"))
        self.assertEqual(second.action, "updated")
        self.assertNotEqual(second.backup, result.backup)

    def test_foreign_entry_needs_force(self):
        path = self.project / ".mcp.json"
        foreign = {"mcpServers": {"persistent-memory": {"command": "npx", "args": ["@other/memory"]}}}
        path.write_text(json.dumps(foreign))
        with self.assertRaisesRegex(SetupError, "does not run persistent-memory"):
            self.setup("claude-code", scope="project")
        self.assertEqual(json.loads(path.read_text()), foreign)
        self.assertFalse(self.store.exists())
        with self.assertRaisesRegex(SetupError, "--force"):
            self.setup("claude-code", scope="project", remove=True)
        self.assertEqual(self.setup("claude-code", scope="project", force=True).action, "updated")
        self.assertEqual(json.loads(path.read_text())["mcpServers"]["persistent-memory"], self.entry(type="stdio"))

    def test_unparsable_file_is_left_alone(self):
        path = self.home / ".cursor" / "mcp.json"
        path.parent.mkdir()
        text = '{\n  // comment\n  "mcpServers": {}\n}\n'
        path.write_text(text)
        with self.assertRaises(SetupError) as caught:
            self.setup("cursor")
        self.assertIn("Add this by hand", str(caught.exception))
        self.assertIn(json.dumps(sys.executable), str(caught.exception))
        self.assertEqual(path.read_text(), text)
        path.write_text('{"mcpServers": []}')
        with self.assertRaisesRegex(SetupError, "expected shape"):
            self.setup("cursor")

    def test_remove(self):
        path = self.home / ".cursor" / "mcp.json"
        self.assertEqual(self.setup("cursor", remove=True).action, "absent")
        self.assertFalse(path.exists())
        path.parent.mkdir()
        path.write_text(json.dumps({"mcpServers": {"keep": {"command": "x"}}}))
        self.setup("cursor")
        result = self.setup("cursor", remove=True)
        self.assertEqual(result.action, "removed")
        self.assertEqual(json.loads(path.read_text()), {"mcpServers": {"keep": {"command": "x"}}})
        self.assertIsNotNone(result.backup)

    def test_dry_run_writes_nothing(self):
        result = self.setup("cursor", scope="project", dry_run=True)
        self.assertEqual(result.action, "added")
        self.assertFalse((self.project / ".cursor").exists())
        self.assertFalse(self.store.exists())
        self.assertTrue(any("dry run" in n for n in result.notes))

    @unittest.skipUnless(os.name == "posix", "symlinks need POSIX permissions in this test")
    def test_symlinked_file_is_followed(self):
        real = self.root / "dotfiles" / "mcp.json"
        real.parent.mkdir()
        real.write_text("{}")
        link = self.home / ".cursor" / "mcp.json"
        link.parent.mkdir()
        link.symlink_to(real)
        self.setup("cursor")
        self.assertTrue(link.is_symlink())
        self.assertIn("persistent-memory", json.loads(real.read_text())["mcpServers"])

    def test_vscode_user_and_shared_project_file(self):
        self.ctx.env["COPILOT_HOME"] = str(self.root / "copilot")
        self.setup("copilot")
        data = json.loads((self.root / "copilot" / "mcp-config.json").read_text())
        self.assertEqual(data["mcpServers"]["persistent-memory"], {**self.entry(type="stdio"), "tools": ["*"]})
        self.assertEqual(list(data["mcpServers"]["persistent-memory"])[0], "type")
        self.assertEqual(self.setup("vscode", scope="project").action, "added")
        self.assertEqual(self.setup("claude-code", scope="project").action, "unchanged")

    def test_claude_desktop_locations(self):
        ctx = self.ctx
        self.assertEqual(cs.claude_desktop_config(ctx), self.home / ".config/Claude/claude_desktop_config.json")
        ctx.platform = "darwin"
        self.assertEqual(cs.claude_desktop_config(ctx),
                         self.home / "Library/Application Support/Claude/claude_desktop_config.json")
        ctx.platform = "win32"
        ctx.env.update(APPDATA=str(self.root / "Roaming"), LOCALAPPDATA=str(self.root / "Local"))
        self.assertEqual(cs.claude_desktop_config(ctx), self.root / "Roaming/Claude/claude_desktop_config.json")
        packaged = self.root / "Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Roaming/Claude"
        packaged.mkdir(parents=True)
        self.assertEqual(cs.claude_desktop_config(ctx), packaged / "claude_desktop_config.json")
        (self.root / "Roaming/Claude").mkdir(parents=True)
        self.assertEqual(cs.claude_desktop_config(ctx), self.root / "Roaming/Claude/claude_desktop_config.json")

    def test_configured_command_serves_mcp(self):
        self.setup("cursor", workspace="team")
        entry = json.loads((self.home / ".cursor" / "mcp.json").read_text())["mcpServers"]["persistent-memory"]
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                                "clientInfo": {"name": "t", "version": "0"}}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                     "params": {"name": "memory_remember", "arguments": {"text": "port 9400 at preprod"}}}]
        proc = subprocess.run([entry["command"]] + entry["args"],
                              input="".join(json.dumps(m) + "\n" for m in messages).encode(),
                              capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        replies = [json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "persistent-memory")
        self.assertFalse(replies[1]["result"].get("isError"), replies[1])
        from hermes_memory.persistent import PersistentMemory
        hits = PersistentMemory(self.store, "team").search("9400")
        self.assertEqual(len(hits["items"]), 1)


class CodexTest(SetupCase):
    def config(self):
        return self.home / ".codex" / "config.toml"

    def test_add_keeps_text_and_is_idempotent(self):
        path = self.config()
        path.parent.mkdir()
        original = '# my settings\nmodel = "o3"\n\n[mcp_servers.docs]\ncommand = "npx"  # keep\nargs = ["d"]\n'
        path.write_text(original)
        self.assertEqual(self.setup("codex").action, "added")
        text = path.read_text()
        self.assertTrue(text.startswith(original))
        data = tomllib.loads(text)
        self.assertEqual(data["mcp_servers"]["persistent-memory"], self.entry())
        self.assertEqual(data["model"], "o3")
        self.assertEqual(self.setup("codex").action, "unchanged")
        self.assertEqual(path.read_text(), text)

    def test_update_replaces_table_and_subtables(self):
        path = self.config()
        path.parent.mkdir()
        path.write_text('[mcp_servers.persistent-memory]\ncommand = "/old/python"\n'
                        'args = ["-m", "hermes_memory.mcp_server"]\n\n[mcp_servers.persistent-memory.env]\nA = "1"\n'
                        '\n[profiles.fast]\nmodel = "x"\n')
        self.assertEqual(self.setup("codex").action, "updated")
        data = tomllib.loads(path.read_text())
        self.assertEqual(data["mcp_servers"]["persistent-memory"], self.entry())
        self.assertEqual(data["profiles"], {"fast": {"model": "x"}})
        self.assertEqual(self.setup("codex", remove=True).action, "removed")
        after = tomllib.loads(path.read_text())
        self.assertNotIn("persistent-memory", after.get("mcp_servers", {}))
        self.assertEqual(after["profiles"], {"fast": {"model": "x"}})
        self.assertEqual(self.setup("codex", remove=True).action, "absent")

    def test_verification_refuses_collateral_damage(self):
        path = self.config()
        path.parent.mkdir()
        original = 'model = "o3"\n'
        path.write_text(original)
        strip = cs._strip_table
        with mock.patch.object(cs, "_strip_table", lambda text, name: strip(text, name).replace(original, "")):
            path.write_text(original + '\n[mcp_servers.persistent-memory]\ncommand = "/old"\n'
                                       'args = ["-m", "hermes_memory.mcp_server"]\n')
            before = path.read_text()
            with self.assertRaisesRegex(SetupError, "form this tool does not edit"):
                self.setup("codex")
        self.assertEqual(path.read_text(), before)

    def test_inline_entry_and_bad_toml_are_refused(self):
        path = self.config()
        path.parent.mkdir()
        inline = 'mcp_servers = { persistent-memory = { command = "x", args = ["-m", "hermes_memory.mcp_server"] } }\n'
        path.write_text(inline)
        with self.assertRaisesRegex(SetupError, "form this tool does not edit"):
            self.setup("codex")
        self.assertEqual(path.read_text(), inline)
        path.write_text("model = \n")
        with self.assertRaisesRegex(SetupError, "not valid TOML"):
            self.setup("codex")
        path.write_text('[mcp_servers.persistent-memory]\ncommand = "npx"\nargs = ["other"]\n')
        with self.assertRaisesRegex(SetupError, "does not run persistent-memory"):
            self.setup("codex")

    def test_strings_survive_quoting_and_codex_home(self):
        self.ctx.env["CODEX_HOME"] = str(self.root / "codex")
        odd = self.root / 'a "quoted" \\ back\tslash ünï 😀\x7f'
        self.setup("codex", store=str(odd), dry_run=True)
        action, text = cs.plan_toml(self.root / "codex" / "config.toml", "persistent-memory",
                                    {"command": "C:\\Python\\python.exe",
                                     "args": ["--store", str(odd)]})
        self.assertEqual(action, "added")
        self.assertEqual(tomllib.loads(text)["mcp_servers"]["persistent-memory"]["args"][1], str(odd))


class ClaudeUserTest(SetupCase):
    def test_add_unchanged_update_remove(self):
        result = self.setup("claude-code")
        self.assertEqual(result.action, "added")
        self.assertEqual(self.tools.calls[-1][:6], ["/usr/local/bin/claude", "mcp", "add-json", "--scope", "user",
                                                    "persistent-memory"])
        self.assertEqual(json.loads(self.tools.calls[-1][6]), self.entry(type="stdio"))
        calls = len(self.tools.calls)
        self.assertEqual(self.setup("claude-code").action, "unchanged")
        self.assertEqual(len(self.tools.calls), calls)
        self.assertEqual(self.setup("claude-code", workspace="other").action, "updated")
        self.assertEqual([c[2] for c in self.tools.calls[calls:]], ["remove", "add-json"])
        self.assertEqual(self.setup("claude-code", remove=True).action, "removed")
        self.assertEqual(self.setup("claude-code", remove=True).action, "absent")

    def test_foreign_and_missing_cli(self):
        self.tools.claude_file.write_text(json.dumps({"mcpServers": {"persistent-memory": {"command": "npx"}}}))
        with self.assertRaisesRegex(SetupError, "does not run persistent-memory"):
            self.setup("claude-code")
        self.assertEqual(self.tools.calls, [])
        self.on_path.clear()
        with self.assertRaises(SetupError) as caught:
            self.setup("claude-code", name="pm")
        self.assertIn("claude mcp add-json --scope user pm", str(caught.exception))
        self.assertFalse(self.store.exists())


class HermesTest(SetupCase):
    def setUp(self):
        super().setUp()
        bin_dir = self.root / "venv" / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "hermes").write_text("")
        self.ctx.python = str(bin_dir / "python")
        self.provider_file = self.root / "hermes-home" / "persistent-memory" / "config.json"

    def test_provider_in_same_environment(self):
        self.provider_file.parent.mkdir(parents=True)
        self.provider_file.write_text(json.dumps({"top_k": 8, "workspace": "hermes"}))
        result = self.setup("hermes-agent")
        self.assertEqual(result.action, "added")
        self.assertEqual(self.tools.hermes_config, {"memory": {"provider": "persistent-memory"}})
        self.assertEqual(json.loads(self.provider_file.read_text()),
                         {"top_k": 8, "workspace": "default", "store_dir": str(self.store)})
        self.assertIsNotNone(result.backup)
        self.assertEqual(self.setup("hermes-agent").action, "unchanged")
        self.assertEqual(self.setup("hermes-agent", remove=True).action, "removed")
        self.assertEqual(self.tools.hermes_config, {"memory": {}})
        self.assertTrue(self.provider_file.exists())
        self.assertEqual(self.setup("hermes-agent", remove=True).action, "absent")

    def test_other_provider_needs_force(self):
        self.tools.hermes_config = {"memory": {"provider": "honcho"}}
        with self.assertRaisesRegex(SetupError, "honcho"):
            self.setup("hermes-agent")
        self.assertFalse(self.provider_file.exists())
        self.assertEqual(self.setup("hermes-agent", force=True).action, "added")
        self.assertEqual(self.tools.hermes_config["memory"]["provider"], "persistent-memory")

    def test_mcp_mode_when_hermes_is_elsewhere(self):
        os.unlink(self.root / "venv" / "bin" / "hermes")
        with self.assertRaisesRegex(SetupError, "not found"):
            self.setup("hermes-agent")
        self.on_path["hermes"] = "/opt/hermes/bin/hermes"
        with self.assertRaisesRegex(SetupError, "own environment"):
            self.setup("hermes-agent", hermes_mode="provider")
        result = self.setup("hermes-agent")
        self.assertEqual(result.action, "added")
        server = self.tools.hermes_config["mcp_servers"]["persistent-memory"]
        self.assertEqual(server, {**self.entry(), "command": self.ctx.python, "timeout": 60})
        self.assertEqual(self.setup("hermes-agent").action, "updated")
        self.tools.hermes_config["mcp_servers"]["other"] = {"command": "npx", "args": ["x"]}
        with self.assertRaisesRegex(SetupError, "does not run persistent-memory"):
            self.setup("hermes-agent", name="other")
        self.assertEqual(self.setup("hermes-agent", remove=True).action, "removed")
        self.assertNotIn("persistent-memory", self.tools.hermes_config["mcp_servers"])


class ArgumentsAndCliTest(SetupCase):
    def test_refusals(self):
        for kw, pattern in [({"client": "emacs"}, "unknown client"),
                            ({"client": "windsurf", "scope": "project"}, "supports --scope user only"),
                            ({"client": "cursor", "name": "a b"}, "--name"),
                            ({"client": "cursor", "workspace": "a\nb"}, "--workspace")]:
            with self.assertRaisesRegex(SetupError, pattern):
                setup(Request(**kw), self.ctx)

    def test_is_ours(self):
        self.assertTrue(cs.is_ours({"command": "py", "args": ["-m", "hermes_memory.mcp_server"]}))
        self.assertTrue(cs.is_ours({"command": "C:\\v\\Scripts\\persistent-memory-mcp.exe"}))
        self.assertTrue(cs.is_ours({"command": "/v/bin/persistent-memory", "args": ["mcp"]}))
        self.assertFalse(cs.is_ours({"command": "npx", "args": ["@modelcontextprotocol/server-memory"]}))
        self.assertFalse(cs.is_ours({"command": "py", "args": "hermes_memory.mcp_server"}))
        self.assertFalse(cs.is_ours("x"))

    def test_cli_setup_and_status(self):
        env = {"HOME": str(self.home), "XDG_DATA_HOME": str(self.root / "data")}
        with mock.patch.dict(os.environ, env), mock.patch.object(Path, "home", return_value=self.home), \
                mock.patch.object(Path, "cwd", return_value=self.project):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(persistent_cli.main(["setup", "cursor", "--json"]), 0)
            self.assertEqual(json.loads(out.getvalue())["action"], "added")
            self.assertTrue((self.root / "data/persistent-memory/authority/authority.db").exists())
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(persistent_cli.main(["status", "--json"]), 0)
            report = json.loads(out.getvalue())
            self.assertTrue(report["store_exists"])
            states = {(r["client"], r["scope"]): r["state"] for r in report["clients"]}
            self.assertEqual(states[("cursor", "user")], "configured as persistent-memory")
            self.assertEqual(states[("windsurf", "user")], "no file")
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                self.assertEqual(persistent_cli.main(["setup", "windsurf", "--scope", "project"]), 1)
            self.assertIn("supports --scope user only", err.getvalue())

    def test_installed_command(self):
        proc = subprocess.run([sys.executable, "-m", "hermes_memory.persistent_cli", "--version"],
                              capture_output=True, text=True, timeout=60)
        from hermes_memory import __version__
        self.assertEqual(proc.stdout.strip(), "persistent-memory " + __version__)
        proc = subprocess.run([sys.executable, "-m", "hermes_memory.persistent_cli", "mcp", "--help"],
                              capture_output=True, text=True, timeout=60)
        self.assertIn("persistent-memory-mcp", proc.stdout)


if __name__ == "__main__":
    unittest.main()
