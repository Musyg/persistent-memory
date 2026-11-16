"""Proposals that a person approves before they reach the memory.

With persistent-memory-mcp --review, the write tools (remember, derive, correct, withdraw
and learn) do not change the memory. Each call is checked against the tool schema and
kept as a pending proposal in review.db, next to the store. The agent can follow its
proposals with memory_proposal_status but cannot approve them. A person decides with

    persistent-memory review list
    persistent-memory review approve ID
    persistent-memory review reject ID

Approval runs the same tool through PersistentMemory, so every guarantee of a direct write
holds: exact versions, compare-and-swap on corrections, cascade on withdrawal, notices. A
proposal the memory refuses at that moment (a correction whose expected_version is no
longer current, a parent that was withdrawn meanwhile) is marked failed with the refusal
code; it is never forced through. review.db is a sidecar: the core and its pinned bytes
are not involved.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .core import MemoryError, require

__all__ = ["REVIEW_SCHEMA", "WRITE_TOOLS", "Proposals", "apply_proposal"]

REVIEW_SCHEMA = "persistent-memory.review.v1"
WRITE_TOOLS = frozenset({"memory_remember", "memory_derive", "memory_correct", "memory_withdraw",
                         "memory_learn"})
STATES = ("pending", "applying", "approved", "rejected", "failed")
_MAX_NOTE = 500


def _utc(seconds):
    if seconds is None:
        return None
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Proposals:
    """The pending and decided proposals of one store, all workspaces together."""

    def __init__(self, root, *, create=True):
        self.path = Path(root).absolute() / "review.db"
        if not create and not self.path.is_file():
            self.exists = False
            return
        self.exists = True
        with closing(self._connect()) as c, c:
            c.executescript("""
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, workspace TEXT NOT NULL, tool TEXT NOT NULL,
  arguments TEXT NOT NULL, session_id TEXT, created_at REAL NOT NULL, state TEXT NOT NULL,
  decided_at REAL, result TEXT, error TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS proposals_state ON proposals(state, created_at);
""")
            c.execute("INSERT OR IGNORE INTO meta VALUES ('schema', ?)", (REVIEW_SCHEMA,))
            row = c.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            require(row[0] == REVIEW_SCHEMA, "review_schema_mismatch")

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _row(row, *, with_arguments=True):
        out = {"proposal_id": row["id"], "workspace": row["workspace"], "tool": row["tool"],
               "state": row["state"], "session_id": row["session_id"], "created_at": _utc(row["created_at"]),
               "decided_at": _utc(row["decided_at"])}
        if with_arguments:
            out["arguments"] = json.loads(row["arguments"])
        if row["result"] is not None:
            out["result"] = json.loads(row["result"])
        if row["error"] is not None:
            out["error"] = row["error"]
        if row["note"] is not None:
            out["note"] = row["note"]
        return out

    def propose(self, workspace, tool, arguments, session_id=None):
        require(tool in WRITE_TOOLS, "not_a_write_tool")
        proposal_id = "p-" + uuid.uuid4().hex[:16]
        with closing(self._connect()) as c, c:
            c.execute("INSERT INTO proposals(id, workspace, tool, arguments, session_id, created_at, state) "
                      "VALUES (?,?,?,?,?,?, 'pending')",
                      (proposal_id, workspace, tool, json.dumps(arguments, ensure_ascii=False, sort_keys=True),
                       session_id, time.time()))
        return proposal_id

    def get(self, proposal_id, workspace=None):
        if not self.exists:
            raise MemoryError("unknown_proposal")
        with closing(self._connect()) as c:
            row = c.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        require(row is not None and (workspace is None or row["workspace"] == workspace), "unknown_proposal")
        return self._row(row)

    def list(self, *, workspace=None, states=("pending", "applying"), session_id=None, limit=None):
        if not self.exists:
            return []
        query, params = "SELECT * FROM proposals WHERE 1=1", []
        if workspace is not None:
            query += " AND workspace=?"
            params.append(workspace)
        if session_id is not None:
            query += " AND session_id=?"
            params.append(session_id)
        if states:
            query += " AND state IN (%s)" % ",".join("?" * len(states))
            params.extend(states)
        with closing(self._connect()) as c:
            rows = c.execute(query + " ORDER BY created_at, id", params).fetchall()
        if limit is not None:
            rows = rows[-limit:]
        return [self._row(r) for r in rows]

    def _claim(self, proposal_id, state):
        """Move a pending proposal to state; only one decider can win."""
        require(self.exists, "unknown_proposal")
        with closing(self._connect()) as c, c:
            moved = c.execute("UPDATE proposals SET state=?, decided_at=? WHERE id=? AND state='pending'",
                              (state, time.time(), proposal_id)).rowcount
        if moved != 1:
            current = self.get(proposal_id)
            raise MemoryError("proposal_already_" + current["state"])

    def reject(self, proposal_id, note=None):
        if note is not None:
            require(type(note) is str and 0 < len(note) <= _MAX_NOTE, "invalid_note")
        self._claim(proposal_id, "rejected")
        if note is not None:
            with closing(self._connect()) as c, c:
                c.execute("UPDATE proposals SET note=? WHERE id=?", (note, proposal_id))
        return self.get(proposal_id)

    def approve(self, proposal_id, open_memory, note=None):
        """Apply a pending proposal through the memory of its workspace.

        open_memory(workspace) returns a PersistentMemory. The proposal is claimed first, so two
        approvals of the same id cannot both apply it. A refusal by the memory marks it failed.
        """
        if note is not None:
            require(type(note) is str and 0 < len(note) <= _MAX_NOTE, "invalid_note")
        proposal = self.get(proposal_id)
        require(proposal["state"] == "pending", "proposal_already_" + proposal["state"])
        memory = open_memory(proposal["workspace"])  # a store that cannot open leaves it pending
        self._claim(proposal_id, "applying")
        try:
            result = apply_proposal(memory, proposal)
        except (MemoryError, ValueError, TypeError) as exc:
            self._finish(proposal_id, "failed", error=str(exc) or type(exc).__name__, note=note)
        else:
            # Any other exception (I/O error, interruption) propagates and leaves the proposal
            # 'applying': its outcome is unknown, and a person checks the memory before deciding.
            self._finish(proposal_id, "approved", result=result, note=note)
        return self.get(proposal_id)

    def _finish(self, proposal_id, state, *, result=None, error=None, note=None):
        with closing(self._connect()) as c, c:
            c.execute("UPDATE proposals SET state=?, decided_at=?, result=?, error=?, note=? "
                      "WHERE id=? AND state='applying'",
                      (state, time.time(), None if result is None else json.dumps(result, ensure_ascii=False),
                       error, note, proposal_id))


def apply_proposal(memory, proposal):
    """Run the proposed tool call through the same checks and code path as a direct call."""
    from .mcp_server import Toolbox
    toolbox = Toolbox(memory)
    name, args = proposal["tool"], dict(proposal["arguments"])
    require(name in WRITE_TOOLS and name in toolbox.names(), "not_a_write_tool")
    require(memory.workspace == proposal["workspace"], "scope_mismatch")
    args = toolbox._absent_nulls(name, args)
    toolbox._check(name, args)
    if name == "memory_withdraw" and "event_id" not in args:
        args["event_id"] = "review-" + proposal["proposal_id"]
    return toolbox._run(name, args, proposal["session_id"])
