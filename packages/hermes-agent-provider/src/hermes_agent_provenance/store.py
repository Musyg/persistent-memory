"""Profile-bound wrapper over hermes-memory-core, plus a per-session exposure ledger.

The memory library decides what is allowed to be read. This module adds one thing the
library cannot know: which validated sources were already shown to which Hermes session.
That ledger lets the provider warn a session when a source it used earlier is withdrawn.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from hermes_memory import Authority, Memory
from hermes_memory.typed_memory import KINDS, TypedMemory

# Reasons that mean "we could not check", not "this source is withdrawn".
UNCHECKABLE = {"authority_or_store_unavailable", "content_missing"}
_WORD = re.compile(r"\w+", re.UNICODE)
_VALIDATE_BATCH = 256
_MAX_QUERY_TOKENS = 32


def canonical_ref(ref: dict[str, Any]) -> str:
    return json.dumps(ref, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def search_terms(text: str) -> str:
    """Keep the words that can discriminate (3+ characters), capped below the library limit."""
    words = [w for w in _WORD.findall(text or "") if len(w) >= 3]
    return " ".join(words[:_MAX_QUERY_TOKENS])


class Store:
    """One store per Hermes profile. Every call is serialized: the library uses SQLite
    transactions, and the exposure ledger must not interleave with a revocation check."""

    def __init__(self, root: Path, workspace: str) -> None:
        self.root = Path(root)
        self.workspace = workspace
        self._lock = threading.RLock()
        self.root.mkdir(parents=True, exist_ok=True)
        authority_path = self.root / "authority" / "authority.db"
        anchor_path = self.root / "anchor" / "checkpoint.json"
        if authority_path.exists():
            authority = Authority.open(authority_path, anchor_path)
            memory = Memory.open(self.root / "content.db", authority)
        else:
            authority_path.parent.mkdir(parents=True, exist_ok=True)
            anchor_path.parent.mkdir(parents=True, exist_ok=True)
            authority = Authority.create(authority_path, anchor_path)
            memory = Memory.create(self.root / "content.db", authority)
        self.memory = memory
        self.typed = TypedMemory(memory, self.root / "index.db")
        self._ledger = self.root / "exposure.db"
        with closing(self._connect()) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS exposure(
                  session_id TEXT NOT NULL, ref TEXT NOT NULL, source_id TEXT NOT NULL,
                  via TEXT NOT NULL, first_seen REAL NOT NULL, PRIMARY KEY(session_id, ref));
                CREATE TABLE IF NOT EXISTS notified(
                  session_id TEXT NOT NULL, ref TEXT NOT NULL, notified_at REAL NOT NULL,
                  PRIMARY KEY(session_id, ref));
                CREATE TABLE IF NOT EXISTS withdrawals(
                  event_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, reason TEXT NOT NULL,
                  session_id TEXT NOT NULL, at REAL NOT NULL);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._ledger, timeout=5)

    # -- reads -----------------------------------------------------------------------------

    def search(self, query: str, *, kinds: Optional[list[str]] = None, top_k: int = 5,
               max_chars: int = 2000) -> dict[str, Any]:
        terms = search_terms(query)
        if not terms:
            return {"status": "completed", "items": [], "exclusions": []}
        with self._lock:
            def run() -> dict[str, Any]:
                return self.typed.search(self.workspace, terms, as_of=utc_now(), evidence_kinds=kinds,
                                         top_k=top_k, max_context_chars=max_chars)
            result = run()
            if result.get("status") == "index_stale":
                self.typed.sync(self.workspace)
                result = run()
            return result

    def explain(self, source_id: str) -> dict[str, Any]:
        with self._lock:
            plan = self.memory.plan_revocation(self.workspace, source_id)
            own = [r for r in plan["affected"] if r["artifact_id"] == source_id]
            if not own:
                raise LookupError("unknown_source")
            return {"source_id": source_id, "versions": [self.memory.explain_artifact(r) for r in own],
                    "dependents": [r for r in plan["affected"] if r["artifact_id"] != source_id],
                    "coverage": plan["coverage"]}

    # -- writes ----------------------------------------------------------------------------

    def remember(self, text: str, kind: str, aliases: Optional[list[str]] = None) -> dict[str, Any]:
        if kind not in KINDS:
            raise ValueError("invalid_evidence_kind")
        attributes: dict[str, Any] = {"evidence_kind": kind, "observed_at": utc_now()}
        if aliases:
            attributes["aliases"] = aliases
        source_id = "m-" + uuid.uuid4().hex[:16]
        with self._lock:
            out = self.typed.put(self.workspace, source_id, text, attributes)
            self.memory.drain_outbox()
            self.typed.sync(self.workspace)
        return {"source_id": source_id, "version_id": out["ref"]["version_id"]}

    def withdraw(self, source_id: str, reason: str, session_id: str) -> dict[str, Any]:
        with self._lock:
            plan = self.memory.plan_revocation(self.workspace, source_id)
            if not any(r["artifact_id"] == source_id for r in plan["affected"]):
                raise LookupError("unknown_source")
            event_id = "w-" + uuid.uuid4().hex
            result = self.memory.revoke_source(self.workspace, source_id, event_id)
            self.memory.drain_outbox()
            self.typed.sync(self.workspace)
            with closing(self._connect()) as conn, conn:
                conn.execute("INSERT INTO withdrawals VALUES (?,?,?,?,?)",
                             (event_id, source_id, reason, session_id, time.time()))
        return {**result, "source_id": source_id, "dependents_blocked": len(plan["affected"]) - 1}

    # -- exposure ledger -------------------------------------------------------------------

    def record_exposure(self, session_id: str, refs: Iterable[dict[str, Any]], via: str) -> None:
        if not session_id:
            return
        rows = [(session_id, canonical_ref(r), r["artifact_id"], via, time.time()) for r in refs]
        if rows:
            with closing(self._connect()) as conn, conn:
                conn.executemany("INSERT OR IGNORE INTO exposure VALUES (?,?,?,?,?)", rows)

    def _blocked(self, refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        blocked = []
        for start in range(0, len(refs), _VALIDATE_BATCH):
            decisions = self.memory.validate(refs[start:start + _VALIDATE_BATCH])["decisions"]
            blocked += [d for d in decisions if not d["allowed"] and d["reason"] not in UNCHECKABLE]
        return blocked

    def withdrawn_since_shown(self, session_id: str) -> list[dict[str, Any]]:
        """Sources shown to this session that are no longer readable, not yet notified."""
        if not session_id:
            return []
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT ref FROM exposure WHERE session_id=? AND ref NOT IN "
                "(SELECT ref FROM notified WHERE session_id=?)", (session_id, session_id)).fetchall()
            return self._blocked([json.loads(r[0]) for r in rows])

    def mark_notified(self, session_id: str, refs: Iterable[dict[str, Any]]) -> None:
        rows = [(session_id, canonical_ref(r), time.time()) for r in refs]
        if rows:
            with closing(self._connect()) as conn, conn:
                conn.executemany("INSERT OR IGNORE INTO notified VALUES (?,?,?)", rows)

    def exposure_report(self) -> list[dict[str, Any]]:
        """Every session that was shown a source which is withdrawn now."""
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute("SELECT session_id, ref, via, first_seen FROM exposure").fetchall()
            refs = {r[1]: json.loads(r[1]) for r in rows}
            blocked = {canonical_ref(d["ref"]): d["reason"] for d in self._blocked(list(refs.values()))}
            notified = {(s, r) for s, r in conn.execute("SELECT session_id, ref FROM notified")}
        report: dict[str, list[dict[str, Any]]] = {}
        for session_id, ref, via, first_seen in rows:
            if ref in blocked:
                report.setdefault(session_id, []).append(
                    {"ref": refs[ref], "reason": blocked[ref], "via": via, "first_seen": first_seen,
                     "session_notified": (session_id, ref) in notified})
        return [{"session_id": s, "withdrawn_sources": items} for s, items in sorted(report.items())]
