"""Typed, bounded retrieval over the pinned local Hermes memory v0.1 authority.

The SQLite FTS index is a discardable candidate projection, never an authority.
"""

from datetime import datetime
from contextlib import closing, contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys

CORE_SHA = "5ad093031bb061360c616ed44ab321499f3765b7e887928d073ee20ed6a37bb0"
SCHEMA = "hermes.typed-memory.v1"
KINDS = {"document", "observation", "hypothesis", "procedure", "task", "feedback"}


class RetrievalError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise RetrievalError(reason)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def timestamp(value):
    require(value is None or type(value) is str, "invalid_timestamp")
    if value is None:
        return None
    require(0 < len(value) <= 40 and value.endswith("Z") and "T" in value, "utc_timestamp_required")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RetrievalError("invalid_timestamp") from exc
    return result


def conditions(value):
    require(type(value) is dict and len(value) <= 32, "invalid_conditions")
    for key, item in value.items():
        require(type(key) is str and 0 < len(key) <= 128, "invalid_condition_key")
        require(type(item) in {str, bool, int}, "invalid_condition_value")
        if type(item) is str:
            require(len(item) <= 512, "condition_value_limit")
        if type(item) is int:
            require(abs(item) <= 2**53, "condition_integer_limit")
    return dict(value)


def metadata(value):
    require(type(value) is dict, "invalid_metadata")
    fields = {"evidence_kind", "valid_from", "valid_until", "observed_at", "aliases", "preconditions", "confidence"}
    require(set(value) <= fields, "unknown_metadata_field")
    kind = value.get("evidence_kind", "document")
    require(type(kind) is str and kind in KINDS, "invalid_evidence_kind")
    result = {"evidence_kind": kind, "valid_from": value.get("valid_from"), "valid_until": value.get("valid_until"), "observed_at": value.get("observed_at"), "aliases": value.get("aliases", []), "preconditions": conditions(value.get("preconditions", {})), "confidence": value.get("confidence")}
    start, end = timestamp(result["valid_from"]), timestamp(result["valid_until"])
    timestamp(result["observed_at"])
    require(start is None or end is None or start < end, "empty_validity_interval")
    aliases = result["aliases"]
    require(type(aliases) is list and len(aliases) <= 32, "invalid_aliases")
    require(all(type(alias) is str and 0 < len(alias) <= 512 for alias in aliases), "invalid_alias")
    require(len({alias.casefold() for alias in aliases}) == len(aliases), "duplicate_alias")
    confidence = result["confidence"]
    require(confidence is None or (type(confidence) in {int, float} and math.isfinite(confidence) and 0 <= confidence <= 1), "invalid_declared_confidence")
    return result


def decode(content):
    try:
        envelope = json.loads(content)
    except (ValueError, TypeError):
        return None
    if type(envelope) is not dict or envelope.get("schema") != SCHEMA:
        return None
    require(set(envelope) == {"schema", "text", "metadata"}, "invalid_envelope")
    require(type(envelope["text"]) is str and len(envelope["text"].encode("utf-8")) <= 512000, "invalid_text")
    return {"schema": SCHEMA, "text": envelope["text"], "metadata": metadata(envelope["metadata"])}


class CoreV01Adapter:
    """Explicit, hash-pinned adapter; no claims of arbitrary core compatibility."""

    def __init__(self, memory):
        self.memory = memory
        self.module = sys.modules[type(memory).__module__]
        path = Path(self.module.__file__)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == CORE_SHA, "unsupported_core_version")

    def snapshot(self, workspace, limit, max_content_bytes):
        with self.memory.authority.transaction() as authority, closing(self.module.connect(self.memory.path, True)) as data:
            data.execute("BEGIN")
            cp = self.memory.authority._checkpoint(authority)
            heads = authority.execute("SELECT artifact_id,version_id FROM heads WHERE workspace=? ORDER BY artifact_id LIMIT ?", (workspace, limit + 1)).fetchall()
            require(len(heads) <= limit, "sync_document_limit")
            rows = []
            excluded = 0
            content_bytes = 0
            for head in heads:
                ref = {"workspace": workspace, "artifact_id": head[0], "version_id": head[1]}
                item = self.memory._read(authority, data, ref)
                if not item["allowed"]:
                    require(item["reason"] != "content_missing", "content_missing")
                    excluded += 1
                    continue
                content_bytes += len(item["content"].encode("utf-8"))
                require(content_bytes <= max_content_bytes, "sync_content_bytes_limit")
                envelope = decode(item["content"])
                rows.append((ref, envelope))
            return cp, rows, excluded, content_bytes


class TypedMemory:
    def __init__(self, memory, index_path):
        self.core = CoreV01Adapter(memory)
        self.memory = memory
        raw_path = Path(index_path).absolute()
        require(not raw_path.is_symlink(), "index_symlink_forbidden")
        self.index_path = raw_path.resolve()
        require(self.index_path not in {memory.path, memory.authority.path, memory.authority.anchor_path}, "index_must_be_separate")
        exists = self.index_path.exists()
        if not exists:
            fd = os.open(self.index_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        try:
            with self._transaction() as connection:
                if exists:
                    schema = connection.execute("SELECT version FROM index_schema").fetchone()
                    require(schema is not None and schema[0] == SCHEMA, "index_schema_mismatch")
                else:
                    connection.executescript("""
CREATE TABLE index_schema(version TEXT NOT NULL);
CREATE TABLE checkpoints(workspace TEXT PRIMARY KEY, generation TEXT NOT NULL, epoch INTEGER NOT NULL, unmanaged INTEGER NOT NULL, excluded INTEGER NOT NULL);
CREATE TABLE documents(row_id INTEGER PRIMARY KEY, workspace TEXT NOT NULL, source_id TEXT NOT NULL, ref TEXT NOT NULL UNIQUE);
CREATE INDEX workspace_documents ON documents(workspace,source_id);
CREATE TABLE aliases(workspace TEXT NOT NULL, alias TEXT NOT NULL, row_id INTEGER NOT NULL);
CREATE INDEX alias_lookup ON aliases(workspace,alias);
CREATE VIRTUAL TABLE lexical USING fts5(text, tokenize='unicode61');
""")
                    connection.execute("INSERT INTO index_schema VALUES (?)", (SCHEMA,))
        except sqlite3.Error as exc:
            raise RetrievalError("index_backend_unavailable") from exc

    def _connect(self):
        connection = sqlite3.connect(self.index_path.as_uri() + "?mode=rw", uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @contextmanager
    def _transaction(self):
        with closing(self._connect()) as connection:
            with connection:
                yield connection

    def put(self, workspace, source_id, text, attributes, expected_version=None):
        require(type(text) is str and len(text.encode("utf-8")) <= 512000, "invalid_text")
        envelope = canonical({"schema": SCHEMA, "text": text, "metadata": metadata(attributes)})
        return self.memory.register_source(workspace, source_id, envelope, expected_version=expected_version)

    def sync(self, workspace, max_documents=5000, max_content_bytes=32 * 1024 * 1024):
        self.core.module.name(workspace)
        require(type(max_documents) is int and 0 < max_documents <= 5000, "invalid_sync_limit")
        require(type(max_content_bytes) is int and 0 < max_content_bytes <= 128 * 1024 * 1024, "invalid_sync_bytes_limit")
        cp, rows, excluded, content_bytes = self.core.snapshot(workspace, max_documents, max_content_bytes)
        unmanaged = sum(envelope is None for _, envelope in rows)
        with self._transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            ids = [row[0] for row in connection.execute("SELECT row_id FROM documents WHERE workspace=?", (workspace,))]
            for row_id in ids:
                connection.execute("DELETE FROM lexical WHERE rowid=?", (row_id,))
            connection.execute("DELETE FROM aliases WHERE workspace=?", (workspace,))
            connection.execute("DELETE FROM documents WHERE workspace=?", (workspace,))
            for ref, envelope in rows:
                if envelope is None:
                    continue
                cursor = connection.execute("INSERT INTO documents(workspace,source_id,ref) VALUES (?,?,?)", (workspace, ref["artifact_id"], canonical(ref)))
                row_id = cursor.lastrowid
                connection.execute("INSERT INTO lexical(rowid,text) VALUES (?,?)", (row_id, envelope["text"]))
                labels = {ref["artifact_id"].casefold(), *(alias.casefold() for alias in envelope["metadata"]["aliases"])}
                connection.executemany("INSERT INTO aliases VALUES (?,?,?)", [(workspace, label, row_id) for label in sorted(labels)])
            connection.execute("INSERT OR REPLACE INTO checkpoints VALUES (?,?,?,?,?)", (workspace, cp["generation"], cp["epoch"], unmanaged, excluded))
        return {"epoch": cp["epoch"], "indexed": len(rows) - unmanaged, "unmanaged": unmanaged, "excluded": excluded, "content_bytes": content_bytes, "max_content_bytes": max_content_bytes, "complete_within_bound": True}

    @staticmethod
    def _empty(status, reason):
        return {"status": status, "reason": reason, "items": [], "context": "", "context_empty": True, "complete": False}

    def search(self, workspace, query, *, as_of=None, conditions=None, evidence_kinds=None, top_k=5, max_context_chars=2000, candidate_limit=100):
        self.core.module.name(workspace)
        require(type(query) is str and 0 < len(query) <= 4096, "invalid_query")
        require(type(top_k) is int and 0 < top_k <= 64, "invalid_top_k")
        require(type(max_context_chars) is int and 0 <= max_context_chars <= 64000, "invalid_context_budget")
        require(type(candidate_limit) is int and top_k <= candidate_limit <= 128, "invalid_candidate_limit")
        now = timestamp(as_of)
        inputs = globals()["conditions"]({} if conditions is None else conditions)
        require(evidence_kinds is None or (type(evidence_kinds) is list and len(evidence_kinds) <= len(KINDS) and all(type(kind) is str and kind in KINDS for kind in evidence_kinds)), "invalid_kind_filter")
        try:
            cp = self.memory.checkpoint()
            with self._transaction() as connection:
                connection.execute("BEGIN")
                indexed = connection.execute("SELECT * FROM checkpoints WHERE workspace=?", (workspace,)).fetchone()
                if indexed is None or indexed["generation"] != cp["generation"] or indexed["epoch"] != cp["epoch"]:
                    return self._empty("index_stale", "explicit_sync_required")
                exact = connection.execute("SELECT DISTINCT d.ref,d.source_id FROM aliases a JOIN documents d ON d.row_id=a.row_id WHERE a.workspace=? AND a.alias=? ORDER BY d.source_id LIMIT ?", (workspace, query.casefold(), candidate_limit + 1)).fetchall()
                tokens = re.findall(r"\w+", query.casefold())
                require(len(tokens) <= 64, "query_token_limit")
                lexical = []
                if tokens:
                    match = " OR ".join('"' + token + '"' for token in tokens)
                    lexical = connection.execute("SELECT d.ref,d.source_id FROM lexical JOIN documents d ON d.row_id=lexical.rowid WHERE lexical MATCH ? AND d.workspace=? ORDER BY bm25(lexical),d.source_id LIMIT ?", (match, workspace, candidate_limit + 1)).fetchall()
                candidates = []
                seen = set()
                for row in [*exact, *lexical]:
                    if row["ref"] not in seen:
                        require(type(row["ref"]) is str, "projection_reference_invalid")
                        try:
                            candidate_ref = self.core.module.ref(json.loads(row["ref"]))
                        except (json.JSONDecodeError, self.core.module.MemoryError) as exc:
                            raise RetrievalError("projection_reference_invalid") from exc
                        candidates.append(candidate_ref)
                        seen.add(row["ref"])
                truncated = len(candidates) > candidate_limit
                candidates = candidates[:candidate_limit]
                coverage = {"unmanaged": indexed["unmanaged"], "excluded_at_sync": indexed["excluded"], "candidate_limit": candidate_limit, "candidate_truncated": truncated, "candidate_count": len(candidates)}
            require(all(ref["workspace"] == workspace for ref in candidates), "projection_scope_mismatch")
            decisions = self.memory.validate(candidates)["decisions"]
            require(len(decisions) == len(candidates), "validation_response_count")
            items, exclusions = [], []
            size = 0
            for ref, decision in zip(candidates, decisions):
                require(decision["ref"] == ref, "reference_response_mismatch")
                if not decision["allowed"]:
                    if decision["reason"] in {"authority_or_store_unavailable", "content_missing"}:
                        return self._empty("unavailable", decision["reason"])
                    exclusions.append({"ref": ref, "reason": decision["reason"]})
                    continue
                envelope = decode(decision["content"])
                require(envelope is not None, "managed_envelope_missing")
                attrs = envelope["metadata"]
                reason = None
                start, end = timestamp(attrs["valid_from"]), timestamp(attrs["valid_until"])
                if evidence_kinds is not None and attrs["evidence_kind"] not in evidence_kinds:
                    reason = "evidence_kind_filtered"
                elif (start is not None or end is not None) and now is None:
                    reason = "time_required"
                elif now is not None and ((start is not None and now < start) or (end is not None and now >= end)):
                    reason = "outside_declared_valid_time"
                elif any(key not in inputs or type(inputs[key]) is not type(value) or inputs[key] != value for key, value in attrs["preconditions"].items()):
                    reason = "precondition_unknown_or_false"
                extra = len(envelope["text"]) + (2 if items else 0)
                if reason is None and size + extra > max_context_chars:
                    reason = "context_budget"
                if reason is not None:
                    exclusions.append({"ref": ref, "reason": reason})
                    continue
                if len(items) < top_k:
                    items.append({"ref": ref, "text": envelope["text"], "metadata": attrs})
                    size += extra
            final = self.memory.checkpoint()
            if final != cp:
                return self._empty("epoch_changed", "concurrent_authority_change")
            context = "\n\n".join(item["text"] for item in items)
            return {"status": "completed", "reason": None, "epoch": cp["epoch"], "items": items, "context": context, "context_empty": not context, "context_chars": size, "exclusions": exclusions, "coverage": coverage, "complete": not truncated and coverage["unmanaged"] == 0, "completeness_scope": "indexed_managed_candidates_at_current_epoch_not_all_results_or_history", "backend": "sqlite_fts5+exact_identifier", "historical_version_access": "unsupported", "confidence_policy": "declared_not_ranked", "budget_unit": "python_characters"}
        except RetrievalError as exc:
            if str(exc) in {"projection_reference_invalid", "projection_scope_mismatch", "reference_response_mismatch", "validation_response_count"}:
                return self._empty("unavailable", str(exc))
            raise
        except (self.core.module.MemoryError, OSError, sqlite3.Error) as exc:
            return self._empty("unavailable", str(exc) if isinstance(exc, self.core.module.MemoryError) else type(exc).__name__)
