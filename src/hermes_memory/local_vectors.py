"""Search by meaning without a server: a local vector projection in the store folder.

    persistent-memory-mcp --semantic                   # model run in process (extra [semantic])
    persistent-memory-mcp --semantic --embed-url http://127.0.0.1:11434/v1 --embed-model nomic-embed-text

The vectors live in vectors.db next to the store and hold exact refs, never text. Like the
Qdrant projection, this one only proposes candidates: PersistentMemory reads each one again
through the authority and applies the same kind, validity and precondition rules as the
keyword search, then fuses both rankings. A withdrawn, superseded or invalidated version is
purged at the next synchronization, and a stale vector cannot bring it back anyway, because
revalidation refuses it. Nothing here touches the core or its pinned bytes.

The embeddings come from either an OpenAI-compatible /embeddings endpoint (Ollama, llama.cpp,
vLLM...), with the standard library only, or from fastembed, which runs an ONNX model in the
process: pip install "persistent-memory-mcp[semantic]". The model is downloaded once, into
the store folder, on first use.
"""
from __future__ import annotations

import hashlib
import importlib.util
import math
import sqlite3
import sys
import time
from array import array
from contextlib import closing
from pathlib import Path

from .core import Memory, MemoryError, require

__all__ = ["DEFAULT_MIN_SCORE", "DEFAULT_MODEL", "FastEmbedEmbeddings", "LocalVectorProjection"]

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
DEFAULT_MIN_SCORE = 0.3  # measured for DEFAULT_MODEL, see docs/SEMANTIC.md
MAX_EMBED_CHARS = 8000
RETRY_AFTER = 300  # seconds before a model that failed to load is tried again
_SCHEMA = "persistent-memory.vectors.v1"
_BATCH = 64
_SWAP = sys.byteorder != "little"  # vectors are stored little-endian float32 on every platform

try:  # numpy comes with fastembed; without it the scoring stays in pure Python
    import numpy as _np
except ImportError:  # pragma: no cover - depends on the environment
    _np = None


class FastEmbedEmbeddings:
    """An ONNX embedding model run in the process by fastembed, loaded once and kept."""

    def __init__(self, model=DEFAULT_MODEL, *, cache_dir=None, threads=None):
        require(type(model) is str and model, "invalid_embedding_model")
        if importlib.util.find_spec("fastembed") is None:  # a missing extra is a setup error
            raise MemoryError('semantic_needs_fastembed: pip install "persistent-memory-mcp[semantic]", '
                              "or give --embed-url and --embed-model")
        self.model_name, self.cache_dir, self.threads = model, cache_dir, threads
        self.model_id = "fastembed:" + model
        self._model = None
        self._failed_at = None

    def _loaded(self):
        if self._model is None:
            if self._failed_at is not None and time.monotonic() - self._failed_at < RETRY_AFTER:
                raise OSError("semantic_model_unavailable: %s: retried later" % self.model_name)
            try:
                from fastembed import TextEmbedding
                self._model = TextEmbedding(model_name=self.model_name, threads=self.threads,
                                            cache_dir=None if self.cache_dir is None else str(self.cache_dir))
            except Exception as exc:  # import, download or load failure: keyword search goes on
                self._failed_at = time.monotonic()
                raise OSError("semantic_model_unavailable: %s: %s" % (self.model_name, exc)) from exc
        return self._model

    def prepare(self):
        """Load (and on first use download) the model now rather than inside a tool call."""
        self._loaded()

    @staticmethod
    def _floats(vectors):
        return [[float(x) for x in vector] for vector in vectors]

    def __call__(self, texts):
        """Vectors for stored entries."""
        return self._floats(self._loaded().passage_embed([t[:MAX_EMBED_CHARS] for t in texts]))

    def query(self, texts):
        """Vectors for search queries; some models embed queries and entries differently."""
        return self._floats(self._loaded().query_embed([t[:MAX_EMBED_CHARS] for t in texts]))


def _unit(vector):
    require(type(vector) is list and vector and all(type(x) in (int, float) for x in vector), "invalid_embedding")
    norm = math.sqrt(sum(x * x for x in vector))
    require(norm > 0 and math.isfinite(norm), "invalid_embedding")
    return [x / norm for x in vector]


def _pack(unit):
    values = array("f", unit)
    if _SWAP:  # pragma: no cover - big-endian hosts only
        values.byteswap()
    return values.tobytes()


def _unpack(blob):
    values = array("f")
    values.frombytes(blob)
    if _SWAP:  # pragma: no cover - big-endian hosts only
        values.byteswap()
    return values


class LocalVectorProjection:
    """Vectors in a SQLite file next to the store. Disposable: deleting the file is always safe."""

    name = "local"

    def __init__(self, memory, embed, *, path=None, min_score=0.5, query_prefix="", document_prefix=""):
        require(embed is not None and callable(embed) and getattr(embed, "model_id", None), "embedder_required")
        require(type(query_prefix) is str and type(document_prefix) is str, "invalid_prefix")
        require(type(min_score) in (int, float) and -1 <= min_score <= 1, "invalid_min_score")
        self.memory = memory
        self.embed = embed
        self.path = Path(path) if path is not None else Path(memory.root) / "vectors.db"
        self.query_prefix, self.document_prefix = query_prefix, document_prefix
        self.model_tag = "embed-" + hashlib.sha256(
            (embed.model_id + "\0" + document_prefix).encode("utf-8")).hexdigest()[:16]
        # A vector search always has a nearest neighbour; below this cosine score a candidate is
        # treated as unrelated. The right value depends on the model.
        self.min_score = float(min_score)
        self.status = "new"
        try:
            with closing(self._connect()):
                pass
        except sqlite3.OperationalError:
            raise  # locked or unreachable: never discard a file another process may be using
        except (sqlite3.DatabaseError, MemoryError):
            # Unreadable or from another schema: the file only holds a projection, rebuild it.
            self._discard()
            with closing(self._connect()):
                pass

    def _discard(self):
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(str(self.path) + suffix).unlink(missing_ok=True)

    def _connect(self):
        """A connection to an initialised file; the file may have been deleted since the last call."""
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            with connection:
                connection.executescript("""
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vectors(point_id TEXT PRIMARY KEY, workspace TEXT NOT NULL, model TEXT NOT NULL,
  artifact_id TEXT NOT NULL, version_id TEXT NOT NULL, dim INTEGER NOT NULL, vector BLOB NOT NULL);
CREATE INDEX IF NOT EXISTS vectors_scope ON vectors(workspace, model);
""")
                connection.execute("INSERT OR IGNORE INTO meta VALUES ('schema', ?)", (_SCHEMA,))
                row = connection.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            require(row[0] == _SCHEMA, "vectors_schema_mismatch")
        except BaseException:
            connection.close()
            raise
        return connection

    def _point(self, ref):
        return Memory.point_id(ref, self.model_tag, "0")

    def _current(self):
        """Readable, managed current versions of the workspace, read through the authority."""
        _, rows, _, _ = self.memory.typed.core.snapshot(self.memory.workspace, 5000, 32 * 1024 * 1024)
        return {self._point(ref): (ref, envelope["text"]) for ref, envelope in rows if envelope is not None}

    def _stored(self, c):
        return {row[0] for row in c.execute("SELECT point_id FROM vectors WHERE workspace=? AND model=?",
                                            (self.memory.workspace, self.model_tag))}

    def _embed(self, texts, *, query=False):
        """Vectors from the embedder; any failure there becomes OSError, so search goes on without them."""
        try:
            method = getattr(self.embed, "query", None) if query else None
            vectors = method(texts) if callable(method) else self.embed(texts)
            require(len(vectors) == len(texts), "embedding_count_mismatch")
            return [_unit(vector) for vector in vectors]
        except OSError:
            raise
        except Exception as exc:
            raise OSError("semantic_embedding_failed: %s" % (str(exc) or type(exc).__name__)) from exc

    def _purge_model(self):
        with closing(self._connect()) as c, c:
            c.execute("DELETE FROM vectors WHERE workspace=? AND model=?", (self.memory.workspace, self.model_tag))

    def sync(self):
        """Purge vectors that no longer match a readable current version, then add missing ones."""
        try:
            return self._sync()
        except sqlite3.Error as exc:
            raise OSError("vectors_unavailable: %s" % exc) from exc

    def _sync(self):
        prepare = getattr(self.embed, "prepare", None)
        if callable(prepare):
            try:
                prepare()
            except OSError:
                raise
            except Exception as exc:
                raise OSError("semantic_model_unavailable: %s" % exc) from exc
        wanted = self._current()
        with closing(self._connect()) as c, c:
            stale = sorted(self._stored(c) - set(wanted))
            c.executemany("DELETE FROM vectors WHERE point_id=?", [(p,) for p in stale])
            present = self._stored(c)
            dims = {row[0] for row in c.execute("SELECT DISTINCT dim FROM vectors WHERE workspace=? AND model=?",
                                                (self.memory.workspace, self.model_tag))}
        missing = [pid for pid in sorted(wanted) if pid not in present]
        for start in range(0, len(missing), _BATCH):
            batch = missing[start:start + _BATCH]
            units = self._embed([self.document_prefix + wanted[pid][1] for pid in batch])
            if dims and {len(u) for u in units} != dims:
                # The model behind the same name now gives another size: start this model over.
                self._purge_model()
                return self._sync()
            rows = []
            for pid, unit in zip(batch, units):
                ref = wanted[pid][0]
                rows.append((pid, ref["workspace"], self.model_tag, ref["artifact_id"], ref["version_id"],
                             len(unit), _pack(unit)))
            with closing(self._connect()) as c, c:
                c.executemany("INSERT OR REPLACE INTO vectors VALUES (?,?,?,?,?,?,?)", rows)
            dims = {len(u) for u in units}
        return {"path": str(self.path), "purged": len(stale), "added": len(missing), "points": len(wanted)}

    def query(self, text, limit):
        """Candidate refs, best first. Never trusted: the caller revalidates every one."""
        try:
            return self._query(text, limit, heal=True)
        except sqlite3.Error as exc:
            raise OSError("vectors_unavailable: %s" % exc) from exc

    def _query(self, text, limit, heal):
        with closing(self._connect()) as c:
            rows = c.execute("SELECT point_id, workspace, artifact_id, version_id, dim, vector FROM vectors "
                             "WHERE workspace=? AND model=?", (self.memory.workspace, self.model_tag)).fetchall()
        if not rows:
            return []
        vector = self._embed([self.query_prefix + text], query=True)[0]
        size = len(vector)
        usable = [r for r in rows if r[4] == size and len(r[5]) == 4 * size]
        if not usable:
            if not heal:
                raise OSError("vector_dimension_mismatch")
            # Stored with another size (the model changed behind its name): rebuild, then search once more.
            self._purge_model()
            self._sync()
            return self._query(text, limit, heal=False)
        if _np is not None:
            matrix = _np.frombuffer(b"".join(r[5] for r in usable), dtype="<f4").reshape(len(usable), size)
            scores = (matrix @ _np.asarray(vector, dtype=_np.float32)).tolist()
        else:
            scores = [sum(a * b for a, b in zip(_unpack(r[5]), vector)) for r in usable]
        ranked = sorted(((s, r) for s, r in zip(scores, usable) if s >= self.min_score),
                        key=lambda pair: (-pair[0], pair[1][0]))
        refs = []
        for _, (pid, workspace, artifact_id, version_id, _, _) in ranked:
            ref = {"workspace": workspace, "artifact_id": artifact_id, "version_id": version_id}
            try:
                if self._point(ref) != pid:
                    continue
            except MemoryError:  # a row that does not even hold a valid ref
                continue
            refs.append(ref)
            if len(refs) == limit:
                break
        return refs
