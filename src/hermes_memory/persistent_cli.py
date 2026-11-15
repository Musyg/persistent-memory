"""persistent-memory: connect clients to the memory, serve it over MCP, show where it is."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from . import __version__
from .interfaces import write_line
from .typed_memory import RetrievalError
from .client_setup import (ALIASES, CLIENTS, DEFAULT_NAME, DEFAULT_WORKSPACE, Context, Request, SetupError,
                           default_store, setup, status)


def _parser():
    parser = argparse.ArgumentParser(prog="persistent-memory", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version="persistent-memory " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)
    names = list(CLIENTS) + list(ALIASES)
    s = sub.add_parser("setup", help="Add (or remove) this memory in a client's configuration",
                       description="Add this memory to a client. Clients: " + ", ".join(CLIENTS) + ".")
    s.add_argument("client", choices=names, metavar="CLIENT", help=", ".join(CLIENTS))
    s.add_argument("--scope", choices=("user", "project"),
                   help="user: every project (default); project: a file in --project-dir to commit or share")
    s.add_argument("--store", help="Store directory; default $PERSISTENT_MEMORY_DIR or the platform data folder")
    s.add_argument("--workspace", default=DEFAULT_WORKSPACE,
                   help="Workspace inside the store; clients with the same store and workspace share memory")
    s.add_argument("--name", default=DEFAULT_NAME, help="Server name in the client (default %(default)s)")
    s.add_argument("--project-dir", help="Project folder for --scope project (default: current folder)")
    s.add_argument("--remove", action="store_true", help="Remove the entry instead of adding it")
    s.add_argument("--force", action="store_true",
                   help="Replace or remove an entry of the same name that runs something else")
    s.add_argument("--dry-run", action="store_true", help="Show what would change; write nothing")
    s.add_argument("--hermes-mode", choices=("auto", "provider", "mcp"), default="auto",
                   help="hermes-agent: memory provider (same environment) or MCP server (default: auto)")
    s.add_argument("--hermes-command", help="hermes-agent: path to the hermes command")
    s.add_argument("--json", action="store_true", help="Print the result as JSON")
    st = sub.add_parser("status", help="Show the default store and which client files run this memory")
    st.add_argument("--project-dir")
    st.add_argument("--json", action="store_true")
    sub.add_parser("mcp", help="Run the MCP server (same options as persistent-memory-mcp)", add_help=False)
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["mcp"]:
        from .mcp_server import main as serve
        return serve(argv[1:])
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except (RetrievalError, sqlite3.Error, OSError) as exc:
        from .mcp_server import start_message
        print("persistent-memory: cannot run: " + start_message(exc), file=sys.stderr)
        return 2


def _run(args):
    if args.command == "status":
        ctx = Context.current()
        store = default_store(ctx.env, ctx.platform, ctx.home)
        report = {"version": __version__, "python": ctx.python, "default_store": str(store),
                  "store_exists": (store / "authority" / "authority.db").exists(),
                  "clients": status(ctx, args.project_dir)}
        if args.json:
            write_line(json.dumps(report, indent=2))
        else:
            write_line("persistent-memory %s (%s)" % (report["version"], report["python"]))
            write_line("default store: %s%s" % (store, "" if report["store_exists"] else " (not created yet)"))
            for row in report["clients"]:
                write_line("  %-15s %-8s %-28s %s" % (row["client"], row["scope"], row["state"], row["file"]))
            write_line("Hermes Agent is not listed: run persistent-memory setup hermes-agent --dry-run")
        return 0
    request = Request(client=args.client, scope=args.scope, store=args.store, workspace=args.workspace,
                      name=args.name, project_dir=args.project_dir, remove=args.remove, force=args.force,
                      dry_run=args.dry_run, hermes_mode=args.hermes_mode, hermes_command=args.hermes_command)
    try:
        result = setup(request)
    except SetupError as exc:
        print("persistent-memory setup: " + str(exc), file=sys.stderr)
        return 1
    if args.json:
        write_line(json.dumps(result.__dict__, indent=2))
        return 0
    write_line("%s (%s): %s %s in %s" % (result.client, result.scope, result.action, args.name, result.target))
    for command in result.commands:
        write_line("  command: " + command)
    if result.backup:
        write_line("  backup: " + result.backup)
    for note in result.notes:
        write_line("  " + note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
