"""One operations surface over the memory authority.

Every adapter (Python, MCP, Hermes Agent, HTTP) goes through this class, so each one
exposes the same memory:

1. read an exact version through current authority, with the refusal reason;
2. search admissible current versions;
3. remember a new source;
4. derive an artifact from exact parent versions;
5. correct an artifact with compare-and-swap;
6. explain what an artifact depends on and what depends on it (metadata only);
7. plan a withdrawal, then withdraw with cascade;
8. learn a lesson from a task trace and its feedback;
9. keep an exposure ledger and tell a session what it was shown that is no longer valid.

Authority stays in hermes_memory.core. The search index (index.db) and the ledger
(ledger.db) are disposable sidecars: neither ever decides what may be read.
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

from . import core
from .core import Authority, Memory, MemoryError, canonical, name, require
from .typed_memory import KINDS, SCHEMA as TYPED_SCHEMA, RetrievalError, TypedMemory, decode
from .typed_memory import canonical as envelope_json, metadata as typed_metadata

__all__ = ["PersistentMemory", "OPERATIONS", "KINDS", "RELATIONS", "STATES", "utc_now"]

LEDGER_SCHEMA = "persistent-memory.ledger.v1"
OPERATIONS = ("read", "search", "remember", "derive", "correct", "explain", "plan_withdrawal",
              "withdraw", "learn", "record_exposure", "notices", "exposure_report")
# derives and indexes carry invalidation to the child; cites keeps a link without it.
RELATIONS = ("derives", "indexes", "cites")
# Refusal reasons from the authority, and what they mean for a reader.
STATES = {"source_revoked": "withdrawn", "invalidated": "invalidated", "archived": "archived",
          "expired": "expired", "version_not_current": "superseded",
          "provenance_unknown": "provenance_unknown", "unknown_ref": "unknown",
          "dependency_cycle_or_depth": "unknown"}
# Reasons that mean "could not check", never "no longer valid".
UNCHECKABLE = frozenset({"authority_or_store_unavailable", "content_missing"})
_WORD = re.compile(r"\w+")
_BATCH = 256
_SHORT_QUERY_TOKENS = 8
_LONG_QUERY_TOKENS = 32
_MAX_REASON = 500


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hex():
    return uuid.uuid4().hex


def _state(reason):
    return "active" if reason == "allowed" else STATES.get(reason, "unavailable")


class PersistentMemory:
    """One workspace of one store. Thread-safe in a process; SQLite serializes processes.

    Layout under root: authority/authority.db, anchor/checkpoint.json (the freshness
    witness, kept apart from content), content.db, index.db, ledger.db.
    """

    def __init__(self, root, workspace="default", *, create=False):
        self.root = Path(root).absolute()
        self.workspace = name(workspace)
        authority_path = self.root / "authority" / "authority.db"
        anchor_path = self.root / "anchor" / "checkpoint.json"
        if authority_path.exists():
            authority = Authority.open(authority_path, anchor_path)
            memory = Memory.open(self.root / "content.db", authority)
        else:
            require(create is True, "store_missing")
            for folder in (self.root, authority_path.parent, anchor_path.parent):
                folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            authority = Authority.create(authority_path, anchor_path)
            memory = Memory.create(self.root / "content.db", authority)
        self.memory = memory
        # TypedMemory pins the exact core bytes; the private reads below rely on that pin.
        self.typed = TypedMemory(memory, self.root / "index.db")
        self._lock = threading.RLock()
        self._ledger = self.root / "ledger.db"
        with closing(self._connect()) as c, c:
            c.executescript("""
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS exposure(session_id TEXT NOT NULL, workspace TEXT NOT NULL, ref TEXT NOT NULL,
  artifact_id TEXT NOT NULL, via TEXT NOT NULL, first_seen REAL NOT NULL, PRIMARY KEY(session_id, ref));
CREATE TABLE IF NOT EXISTS notified(session_id TEXT NOT NULL, ref TEXT NOT NULL, notified_at REAL NOT NULL,
  PRIMARY KEY(session_id, ref));
CREATE TABLE IF NOT EXISTS withdrawals(event_id TEXT PRIMARY KEY, workspace TEXT NOT NULL,
  artifact_id TEXT NOT NULL, mode TEXT NOT NULL, reason TEXT NOT NULL, session_id TEXT, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS experience(lesson_ref TEXT PRIMARY KEY, workspace TEXT NOT NULL,
  trace_ref TEXT NOT NULL, feedback_ref TEXT NOT NULL, at REAL NOT NULL);
""")
            c.execute("INSERT OR IGNORE INTO meta VALUES ('schema', ?)", (LEDGER_SCHEMA,))
            row = c.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            require(row[0] == LEDGER_SCHEMA, "ledger_schema_mismatch")

    # -- plumbing ---------------------------------------------------------------------------

    def _connect(self):
        connection = sqlite3.connect(self._ledger, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _ref(self, value):
        result = core.ref(value)
        require(result["workspace"] == self.workspace, "scope_mismatch")
        return result

    def _head(self, artifact_id):
        name(artifact_id)
        with self.memory.authority.transaction() as c:
            row = c.execute("SELECT version_id FROM heads WHERE workspace=? AND artifact_id=?",
                            (self.workspace, artifact_id)).fetchone()
            if row is None:
                return None
            kind = c.execute("SELECT kind FROM objects WHERE workspace=? AND artifact_id=? AND version_id=?",
                             (self.workspace, artifact_id, row[0])).fetchone()
        return {"ref": {"workspace": self.workspace, "artifact_id": artifact_id, "version_id": row[0]},
                "kind": kind[0] if kind else None}

    def _require_head(self, artifact_id):
        head = self._head(artifact_id)
        require(head is not None, "unknown_artifact")
        return head

    def _settle(self):
        """Purge stale projections, then rebuild the search index at the new epoch."""
        self.memory.drain_outbox()
        self.typed.sync(self.workspace)

    @staticmethod
    def _attributes(kind, aliases, valid_from, valid_until, observed_at, preconditions, confidence):
        require(kind in KINDS, "invalid_evidence_kind")
        attributes = {"evidence_kind": kind}
        for field, value in (("aliases", aliases), ("valid_from", valid_from), ("valid_until", valid_until),
                             ("observed_at", observed_at), ("preconditions", preconditions),
                             ("confidence", confidence)):
            if value is not None:
                attributes[field] = value
        try:
            typed_metadata(attributes)
        except RetrievalError as exc:
            raise MemoryError(str(exc)) from exc
        return attributes

    @staticmethod
    def _envelope(text, attributes):
        require(type(text) is str and text.strip() and len(text.encode("utf-8")) <= 512000, "invalid_text")
        return envelope_json({"schema": TYPED_SCHEMA, "text": text, "metadata": typed_metadata(attributes)})

    def _dependencies(self, parents):
        require(type(parents) is list and 0 < len(parents) <= 64, "invalid_parents")
        result = []
        for parent in parents:
            if type(parent) is dict and set(parent) == {"ref", "relation"}:
                require(parent["relation"] in RELATIONS, "invalid_relation")
                result.append({"ref": self._ref(parent["ref"]), "relation": parent["relation"]})
            else:
                result.append({"ref": self._ref(parent), "relation": "derives"})
        return result

    @staticmethod
    def _present(decision):
        if not decision["allowed"]:
            return {"allowed": False, "ref": decision["ref"], "reason": decision["reason"],
                    "state": _state(decision["reason"])}
        try:
            envelope = decode(decision["content"])
        except RetrievalError as exc:
            raise MemoryError("invalid_envelope") from exc
        return {"allowed": True, "ref": decision["ref"], "reason": "allowed", "state": "active",
                "managed": envelope is not None,
                "text": envelope["text"] if envelope else decision["content"],
                "metadata": envelope["metadata"] if envelope else None,
                "content_sha256": decision["content_sha256"]}

    def _blocked(self, refs):
        blocked = []
        for start in range(0, len(refs), _BATCH):
            decisions = self.memory.validate(refs[start:start + _BATCH])["decisions"]
            blocked += [d for d in decisions if not d["allowed"] and d["reason"] not in UNCHECKABLE]
        return blocked

    def checkpoint(self):
        return self.memory.checkpoint()

    def sync(self):
        with self._lock:
            return self.typed.sync(self.workspace)

    # -- 1. read ----------------------------------------------------------------------------

    def read(self, ref, *, session=None):
        """Read one exact version. A refusal carries the authority's reason."""
        rr = self._ref(ref)
        with self._lock:
            result = self._present(self.memory.read(rr))
            if result["allowed"] and session is not None:
                self.record_exposure(session, [rr], "read")
        return result

    # -- 2. search --------------------------------------------------------------------------

    @staticmethod
    def _terms(query):
        tokens = _WORD.findall(query)
        if len(tokens) <= _SHORT_QUERY_TOKENS:
            return query.strip()
        return " ".join([t for t in tokens if len(t) >= 3][:_LONG_QUERY_TOKENS])

    def search(self, query, *, kinds=None, as_of=None, conditions=None, top_k=5, max_chars=2000,
               session=None):
        """Admissible current versions only. Validity windows are checked at as_of (default now).

        A long natural-language query keeps its words of three characters or more.
        """
        require(type(query) is str and 0 < len(query) <= 4096, "invalid_query")
        terms = self._terms(query)
        as_of = utc_now() if as_of is None else as_of
        if not terms:
            return {"status": "completed", "reason": None, "epoch": self.memory.checkpoint()["epoch"],
                    "items": [], "exclusions": [], "coverage": None, "complete": True, "query_terms": ""}
        with self._lock:
            for _ in range(3):
                result = self.typed.search(self.workspace, terms, as_of=as_of, conditions=conditions,
                                           evidence_kinds=kinds, top_k=top_k, max_context_chars=max_chars)
                if result["status"] == "index_stale":
                    self.typed.sync(self.workspace)
                elif result["status"] != "epoch_changed":
                    break
            items = [{"ref": i["ref"], "artifact_id": i["ref"]["artifact_id"], "text": i["text"],
                      "metadata": i["metadata"]} for i in result["items"]]
            if items and session is not None:
                self.record_exposure(session, [i["ref"] for i in items], "search")
            coverage = result.get("coverage")
            complete = bool(result.get("complete"))
            if (result["status"] == "completed" and not complete and coverage
                    and not coverage["candidate_truncated"] and coverage["unmanaged"]
                    and self.memory.checkpoint()["epoch"] == result["epoch"]
                    and coverage["unmanaged"] == self._readable_experience_parents()):
                # Trace and feedback sources are left out of the index on purpose.
                complete = True
        return {"status": result["status"], "reason": result["reason"], "epoch": result.get("epoch"),
                "items": items, "exclusions": result.get("exclusions", []), "coverage": coverage,
                "complete": complete, "query_terms": terms}

    def _readable_experience_parents(self):
        with closing(self._connect()) as c:
            rows = c.execute("SELECT trace_ref, feedback_ref FROM experience WHERE workspace=?",
                             (self.workspace,)).fetchall()
        refs = sorted({value for row in rows for value in row})
        allowed = 0
        for start in range(0, len(refs), _BATCH):
            batch = [json.loads(r) for r in refs[start:start + _BATCH]]
            allowed += sum(d["allowed"] for d in self.memory.validate(batch)["decisions"])
        return allowed

    # -- 3. remember ------------------------------------------------------------------------

    def remember(self, text, *, kind="observation", source_id=None, aliases=None, valid_from=None,
                 valid_until=None, observed_at=None, preconditions=None, confidence=None):
        """Admit a new source. An existing source_id is refused: use correct()."""
        attributes = self._attributes(kind, aliases, valid_from, valid_until,
                                      observed_at or utc_now(), preconditions, confidence)
        artifact_id = name(source_id) if source_id is not None else "m-" + _hex()[:16]
        content = self._envelope(text, attributes)
        with self._lock:
            out = self.memory.register_source(self.workspace, artifact_id, content)
            self._settle()
        return {"artifact_id": artifact_id, "ref": out["ref"], "epoch": out["epoch"],
                "idempotent": out.get("idempotent", False)}

    # -- 4. derive --------------------------------------------------------------------------

    def derive(self, text, *, parents, kind="procedure", artifact_id=None, expected_version=None,
               expected_epoch=None, aliases=None, valid_from=None, valid_until=None, observed_at=None,
               preconditions=None, confidence=None):
        """Store an artifact made from exact parent versions.

        parents: exact refs (relation "derives") or {"ref": ..., "relation": ...}. At least one
        derives or indexes parent is required; every such parent must be readable now.
        """
        dependencies = self._dependencies(parents)
        attributes = self._attributes(kind, aliases, valid_from, valid_until,
                                      observed_at or utc_now(), preconditions, confidence)
        artifact_id = name(artifact_id) if artifact_id is not None else "d-" + _hex()[:16]
        content = self._envelope(text, attributes)
        with self._lock:
            out = self.memory.derive(self.workspace, artifact_id, content, kind, dependencies,
                                     expected_epoch, expected_version=expected_version)
            self._settle()
        return {"artifact_id": artifact_id, "ref": out["ref"], "epoch": out["epoch"],
                "idempotent": out.get("idempotent", False)}

    # -- 5. correct -------------------------------------------------------------------------

    def correct(self, artifact_id, text, *, expected_version, parents=None, aliases=None,
                valid_from=None, valid_until=None, observed_at=None, preconditions=None,
                confidence=None):
        """Replace the current version if it is still expected_version (compare-and-swap).

        Unspecified metadata is kept from the current version. A derived artifact keeps its
        parents unless new ones are given; they must still be current.
        """
        require(type(expected_version) is str, "invalid_expected_version")
        with self._lock:
            head = self._require_head(artifact_id)
            current = self._present(self.memory.read(head["ref"]))
            base = dict(current.get("metadata") or {})
            kind = base.get("evidence_kind", head["kind"])
            attributes = {"aliases": base.get("aliases") or None, "valid_from": base.get("valid_from"),
                          "valid_until": base.get("valid_until"),
                          "preconditions": base.get("preconditions") or None,
                          "confidence": base.get("confidence")}
            for field, value in (("aliases", aliases), ("valid_from", valid_from),
                                 ("valid_until", valid_until), ("preconditions", preconditions),
                                 ("confidence", confidence)):
                if value is not None:
                    attributes[field] = value
            if head["kind"] == "source":
                require(parents is None, "sources_have_no_parents")
                attributes = self._attributes(kind, observed_at=observed_at or utc_now(), **attributes)
                out = self.memory.register_source(self.workspace, artifact_id,
                                                  self._envelope(text, attributes),
                                                  expected_version=expected_version)
            else:
                if parents is None:
                    root = self.memory.explain_artifact(head["ref"])["nodes"][0]
                    dependencies = root["dependencies"]
                else:
                    dependencies = self._dependencies(parents)
                attributes = self._attributes(head["kind"], observed_at=observed_at or utc_now(),
                                              **attributes)
                out = self.memory.derive(self.workspace, artifact_id, self._envelope(text, attributes),
                                         head["kind"], dependencies, None, expected_version=expected_version)
            self._settle()
        return {"artifact_id": artifact_id, "ref": out["ref"], "epoch": out["epoch"],
                "previous": head["ref"], "idempotent": out.get("idempotent", False)}

    # -- 6. explain -------------------------------------------------------------------------

    def explain(self, target):
        """Metadata only: versions, readability, upstream parents and downstream dependents."""
        with self._lock:
            if type(target) is str:
                head = self._require_head(target)
                root = head["ref"]
            else:
                root = self._ref(target)
                head = self._head(root["artifact_id"])
                require(head is not None, "unknown_artifact")
            graph = self.memory.explain_artifact(root)
            plan = self.memory.plan_revocation(self.workspace, root["artifact_id"])
        node = graph["nodes"][0]
        artifact_id = root["artifact_id"]
        return {"artifact_id": artifact_id, "ref": root, "head": head["ref"],
                "kind": head["kind"], "readable": node["allowed"], "reason": node["reason"],
                "state": _state(node["reason"]), "parents": node["dependencies"],
                "producer": node.get("producer"), "upstream": graph["nodes"][1:],
                "versions": [r for r in plan["affected"] if r["artifact_id"] == artifact_id],
                "dependents": [r for r in plan["affected"] if r["artifact_id"] != artifact_id],
                "coverage": plan["coverage"]}

    # -- 7. withdraw ------------------------------------------------------------------------

    def plan_withdrawal(self, artifact_id):
        """What a withdrawal would block, without changing anything."""
        with self._lock:
            head = self._require_head(artifact_id)
            plan = self.memory.plan_revocation(self.workspace, artifact_id)
        return {"artifact_id": artifact_id,
                "mode": "revoke_source" if head["kind"] == "source" else "invalidate_derived",
                "blocked": plan["affected"],
                "dependents": [r for r in plan["affected"] if r["artifact_id"] != artifact_id],
                "coverage": plan["coverage"], "physical_erasure": False}

    def withdraw(self, artifact_id, reason, *, event_id=None, session=None):
        """Stop every read of an artifact and of everything derived from it.

        A source is revoked (all versions, idempotent per event_id); a derived artifact has
        its current version invalidated. Nothing is physically erased.
        """
        require(type(reason) is str and 0 < len(reason) <= _MAX_REASON, "invalid_reason")
        if session is not None:
            name(session)
        with self._lock:
            head = self._require_head(artifact_id)
            plan = self.memory.plan_revocation(self.workspace, artifact_id)
            if head["kind"] == "source":
                mode = "revoke_source"
                event = name(event_id) if event_id is not None else "w-" + _hex()
                result = self.memory.revoke_source(self.workspace, artifact_id, event)
            else:
                mode = "invalidate_derived"
                event = name(event_id) if event_id is not None else "i-" + _hex()
                status = self.memory.set_status(head["ref"], "invalidated")
                result = {"epoch": status["epoch"], "covered_reads_blocked": True,
                          "coverage": "known_dependencies_only", "physical_erasure": False}
            self._settle()
            with closing(self._connect()) as c, c:
                c.execute("INSERT OR IGNORE INTO withdrawals VALUES (?,?,?,?,?,?,?)",
                          (event, self.workspace, artifact_id, mode, reason, session, time.time()))
        return {**result, "artifact_id": artifact_id, "mode": mode, "event_id": event,
                "blocked": plan["affected"],
                "dependents": [r for r in plan["affected"] if r["artifact_id"] != artifact_id]}

    # -- 8. learn ---------------------------------------------------------------------------

    @staticmethod
    def _raw(value, label):
        content = value if type(value) is str else envelope_json(value)
        require(type(content) is str and content.strip() and len(content.encode("utf-8")) <= 1024 * 1024,
                "invalid_" + label)
        try:
            managed = decode(content) is not None
        except RetrievalError:
            managed = True
        require(not managed, label + "_must_not_be_a_memory_envelope")
        return content

    def learn(self, trace, feedback, lesson, *, kind="procedure", lesson_id=None, aliases=None,
              preconditions=None, valid_from=None, valid_until=None, confidence=None):
        """Keep a task trace and its feedback as provenance, and derive the lesson from both.

        The trace and the feedback stay out of search; only the lesson is retrieved. Withdrawing
        either of them blocks the lesson.
        """
        trace_content = self._raw(trace, "trace")
        feedback_content = self._raw(feedback, "feedback")
        self._attributes(kind, aliases, valid_from, valid_until, None, preconditions, confidence)
        token = _hex()[:16]
        with self._lock:
            trace_out = self.memory.register_source(self.workspace, "xt-" + token, trace_content)
            feedback_out = self.memory.register_source(self.workspace, "xf-" + token, feedback_content)
            try:
                lesson_out = self.derive(lesson, parents=[trace_out["ref"], feedback_out["ref"]], kind=kind,
                                         artifact_id=lesson_id or "xl-" + token, aliases=aliases,
                                         preconditions=preconditions, valid_from=valid_from,
                                         valid_until=valid_until, confidence=confidence)
            except BaseException:
                for parent in ("xt-" + token, "xf-" + token):
                    self.memory.revoke_source(self.workspace, parent, "xr-" + parent)
                self._settle()
                raise
            with closing(self._connect()) as c, c:
                c.execute("INSERT OR IGNORE INTO experience VALUES (?,?,?,?,?)",
                          (canonical(lesson_out["ref"]), self.workspace, canonical(trace_out["ref"]),
                           canonical(feedback_out["ref"]), time.time()))
        return {"lesson": lesson_out, "trace": trace_out["ref"], "feedback": feedback_out["ref"]}

    # -- 9. exposure ledger -----------------------------------------------------------------

    def record_exposure(self, session, refs, via="external"):
        """Note that a session was shown these exact versions."""
        session = name(session)
        name(via)
        now = time.time()
        rows = []
        for value in refs:
            rr = self._ref(value)
            rows.append((session, self.workspace, canonical(rr), rr["artifact_id"], via, now))
        if rows:
            with closing(self._connect()) as c, c:
                c.executemany("INSERT OR IGNORE INTO exposure VALUES (?,?,?,?,?,?)", rows)
        return {"recorded": len(rows)}

    def notices(self, session, *, mark=True):
        """Versions this session was shown that are no longer valid, each reported once."""
        session = name(session)
        with self._lock:
            with closing(self._connect()) as c:
                rows = c.execute(
                    "SELECT ref FROM exposure WHERE session_id=? AND workspace=? AND ref NOT IN "
                    "(SELECT ref FROM notified WHERE session_id=?) ORDER BY first_seen, ref",
                    (session, self.workspace, session)).fetchall()
            blocked = self._blocked([json.loads(r[0]) for r in rows])
            notices = [{"ref": d["ref"], "artifact_id": d["ref"]["artifact_id"], "reason": d["reason"],
                        "state": _state(d["reason"])} for d in blocked]
            if mark and notices:
                now = time.time()
                with closing(self._connect()) as c, c:
                    c.executemany("INSERT OR IGNORE INTO notified VALUES (?,?,?)",
                                  [(session, canonical(n["ref"]), now) for n in notices])
        return {"session": session, "notices": notices}

    def exposure_report(self):
        """Every session shown a version of this workspace that is no longer valid."""
        with self._lock:
            with closing(self._connect()) as c:
                rows = c.execute("SELECT session_id, ref, via, first_seen FROM exposure WHERE workspace=? "
                                 "ORDER BY session_id, first_seen, ref", (self.workspace,)).fetchall()
                notified = {(r[0], r[1]) for r in c.execute("SELECT session_id, ref FROM notified")}
            refs = sorted({r["ref"] for r in rows})
            blocked = {canonical(d["ref"]): d["reason"] for d in self._blocked([json.loads(r) for r in refs])}
        report = {}
        for row in rows:
            if row["ref"] in blocked:
                reason = blocked[row["ref"]]
                report.setdefault(row["session_id"], []).append(
                    {"ref": json.loads(row["ref"]), "reason": reason, "state": _state(reason), "via": row["via"],
                     "first_seen": row["first_seen"],
                     "session_notified": (row["session_id"], row["ref"]) in notified})
        return {"workspace": self.workspace,
                "sessions": [{"session": s, "invalid": items} for s, items in sorted(report.items())]}
