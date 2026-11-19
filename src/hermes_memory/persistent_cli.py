"""persistent-memory: connect clients to the memory, serve it over MCP, review proposals, export notes, show where it is."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

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
    r = sub.add_parser("review", help="List, approve or reject what agents proposed (server run with --review)",
                       description="Proposals made by agents through persistent-memory-mcp --review. "
                                   "Approval applies the proposal with the same checks as a direct write; "
                                   "one the memory refuses at that moment is marked failed, never forced.")
    r.add_argument("action", nargs="?", default="list", choices=("list", "show", "approve", "reject"))
    r.add_argument("proposal_id", nargs="?", help="Required by show, approve and reject")
    r.add_argument("--store", help="Store directory; default $PERSISTENT_MEMORY_DIR or the platform data folder")
    r.add_argument("--workspace", help="list: only this workspace (default: all)")
    r.add_argument("--all", action="store_true", help="list: decided proposals too")
    r.add_argument("--note", help="approve, reject: a short note kept with the decision")
    r.add_argument("--json", action="store_true")
    e = sub.add_parser("export", help="Write the memory as Markdown notes (Obsidian vault or plain links)",
                       description="One-way export: one note per entry the memory serves now, with its "
                                   "provenance links. Run it again to bring the folder up to date; notes "
                                   "edited by hand and files the export did not write are left alone.")
    e.add_argument("output", help="Folder to write: empty, or written by a previous export")
    e.add_argument("--store", help="Store directory; default $PERSISTENT_MEMORY_DIR or the platform data folder")
    e.add_argument("--workspace", action="append", help="Only this workspace (repeatable; default: all)")
    e.add_argument("--style", choices=("obsidian", "markdown"), default="obsidian",
                   help="obsidian: [[wikilinks]] and properties (default); markdown: relative links")
    e.add_argument("--include-withdrawn", action="store_true",
                   help="Also write a short note, without the text, for entries no longer served")
    e.add_argument("--force", action="store_true", help="Overwrite or remove notes edited by hand")
    e.add_argument("--json", action="store_true")
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


def _summary(proposal):
    args = proposal["arguments"]
    text = args.get("text") or args.get("lesson") or args.get("reason") or ""
    target = args.get("artifact_id")
    words = " ".join(str(text).split())
    if len(words) > 72:
        words = words[:69] + "..."
    return ("%s: %s" % (target, words)) if target else words


def _review(args):
    from .core import MemoryError
    from .persistent import PersistentMemory
    from .review import Proposals
    store = Path(args.store).expanduser() if args.store else default_store()
    proposals = Proposals(store, create=False)
    if args.action == "list":
        if args.proposal_id:
            print("persistent-memory review: list takes no proposal id", file=sys.stderr)
            return 1
        rows = proposals.list(workspace=args.workspace, states=None if args.all else ("pending", "applying"))
        if args.json:
            write_line(json.dumps(rows, indent=2, ensure_ascii=False))
            return 0
        if not rows:
            write_line("no proposals waiting in %s" % store)
            return 0
        for row in rows:
            write_line("%s  %-8s  %-12s %-15s %s" % (row["proposal_id"], row["state"], row["workspace"],
                                                   row["tool"].replace("memory_", ""), _summary(row)))
        return 0
    if not args.proposal_id:
        print("persistent-memory review: %s needs a proposal id (see persistent-memory review list)"
              % args.action, file=sys.stderr)
        return 1
    try:
        if args.action == "show":
            out = proposals.get(args.proposal_id)
        elif args.action == "reject":
            out = proposals.reject(args.proposal_id, args.note)
        else:
            out = proposals.approve(args.proposal_id,
                                    lambda workspace: PersistentMemory(store, workspace), args.note)
    except MemoryError as exc:
        print("persistent-memory review: " + str(exc), file=sys.stderr)
        return 1
    if args.json or args.action == "show":
        write_line(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        line = "%s %s" % (out["proposal_id"], out["state"])
        if out.get("error"):
            line += ": " + out["error"]
        elif out.get("result", {}).get("artifact_id"):
            line += ": " + out["result"]["artifact_id"]
        write_line(line)
    return 0 if out["state"] != "failed" else 3


def _export(args):
    from .core import MemoryError
    from .export import export_store
    store = Path(args.store).expanduser() if args.store else default_store()
    try:
        report = export_store(store, args.output, workspaces=args.workspace, style=args.style,
                              include_withdrawn=args.include_withdrawn, force=args.force)
    except MemoryError as exc:
        print("persistent-memory export: " + str(exc), file=sys.stderr)
        return 1
    if args.json:
        write_line(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        write_line("%d note%s in %s (%s): %d written, %d unchanged, %d removed"
                   % (report["notes"], "" if report["notes"] == 1 else "s", report["output"], report["style"],
                      len(report["written"]),
                      len(report["unchanged"]), len(report["removed"])))
        for rel in report["kept_edited"]:
            write_line("  kept, edited by hand: " + rel)
        for rel in report["kept_foreign"]:
            write_line("  kept, not written by the export: " + rel)
    return 3 if report["kept_edited"] or report["kept_foreign"] else 0


def _run(args):
    if args.command == "review":
        return _review(args)
    if args.command == "export":
        return _export(args)
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
