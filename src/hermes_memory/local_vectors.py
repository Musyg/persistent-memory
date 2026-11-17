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
from array import array
from contextlib import closing
from pathlib import Path

from .core import Memory, MemoryError, require

__all__ = ["DEFAULT_MIN_SCORE", "DEFAULT_MODEL", "FastEmbedEmbeddings", "LocalVectorProjection"]

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
DEFAULT_MIN_SCORE = 0.3  # measured for DEFAULT_MODEL, see docs/MCP.md
MAX_EMBED_CHARS = 8000
_SCHEMA = "persistent-memory.vectors.v1"
_BATCH = 64

try:  # numpy comes with fastembed; without it the scoring stays in pure Python
    import numpy as _np
except ImportError:  # pragma: no cover - depends on the environment
    _np = None


class FastEmbedEmbeddings:
    """An ONNX embedding model run in the process by fastembed, loaded on first use."""

    def __init__(self, model=DEFAULT_MODEL, *, cache_dir=None, threads=None):
        require(type(model) is str and model, "invalid_embedding_model")
        if importlib.util.find_spec("fastembed") is None:  # a missing extra is a setup error
            raise MemoryError('semantic_needs_fastembed: pip install "persistent-memory-mcp[semantic]", '
                              "or give --embed-url and --embed-model")
        self.model_name, self.cache_dir, self.threads = model, cache_dir, threads
        self.model_id = "fastembed:" + model
        self._model = None

    def _loaded(self):
        if self._model is None:
            from fastembed import TextEmbedding
            try:
                self._model = TextEmbedding(model_name=self.model_name, threads=self.threads,
                                            cache_dir=None if self.cache_dir is None else str(self.cache_dir))
            except Exception as exc:  # download or load failure: lexical search goes on without it
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


class LocalVectorProjection:
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
        with closing(self._connect()) as c, c:
            c.executescript("""
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vectors(point_id TEXT PRIMARY KEY, workspace TEXT NOT NULL, model TEXT NOT NULL,
  artifact_id TEXT NOT NULL, version_id TEXT NOT NULL, dim INTEGER NOT NULL, vector BLOB NOT NULL);
CREATE INDEX IF NOT EXISTS vectors_scope ON vectors(workspace, model);
""")
            c.execute("INSERT OR IGNORE INTO meta VALUES ('schema', ?)", (_SCHEMA,))
            row = c.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            require(row[0] == _SCHEMA, "vectors_schema_mismatch")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def _point(self, ref):
        return Memory.point_id(ref, self.model_tag, "0")

    def _current(self):
        """Readable, managed current versions of the workspace, read through the authority."""
        _, rows, _, _ = self.memory.typed.core.snapshot(self.memory.workspace, 5000, 32 * 1024 * 1024)
        return {self._point(ref): (ref, envelope["text"]) for ref, envelope in rows if envelope is not None}

    def _stored(self, c):
        return {row[0] for row in c.execute("SELECT point_id FROM vectors WHERE workspace=? AND model=?",
                                            (self.memory.workspace, self.model_tag))}

    def sync(self):
        """Purge vectors that no longer match a readable current version, then add missing ones."""
        prepare = getattr(self.embed, "prepare", None)
        if callable(prepare):
            prepare()
        wanted = self._current()
        with closing(self._connect()) as c, c:
            stale = sorted(self._stored(c) - set(wanted))
            c.executemany("DELETE FROM vectors WHERE point_id=?", [(p,) for p in stale])
            present = self._stored(c)
        missing = [pid for pid in sorted(wanted) if pid not in present]
        for start in range(0, len(missing), _BATCH):
            batch = missing[start:start + _BATCH]
            vectors = self.embed([self.document_prefix + wanted[pid][1] for pid in batch])
            require(len(vectors) == len(batch), "embedding_count_mismatch")
            rows = []
            for pid, vector in zip(batch, vectors):
                unit = _unit(vector)
                ref = wanted[pid][0]
                rows.append((pid, ref["workspace"], self.model_tag, ref["artifact_id"], ref["version_id"],
                             len(unit), array("f", unit).tobytes()))
            with closing(self._connect()) as c, c:
                c.executemany("INSERT OR REPLACE INTO vectors VALUES (?,?,?,?,?,?,?)", rows)
        return {"path": str(self.path), "purged": len(stale), "added": len(missing), "points": len(wanted)}

    def _query_vector(self, text):
        texts = [self.query_prefix + text]
        query = getattr(self.embed, "query", None)
        return _unit((query(texts) if callable(query) else self.embed(texts))[0])

    def query(self, text, limit):
        """Candidate refs, best first. Never trusted: the caller revalidates every one."""
        with closing(self._connect()) as c:
            rows = c.execute("SELECT point_id, workspace, artifact_id, version_id, dim, vector FROM vectors "
                             "WHERE workspace=? AND model=?", (self.memory.workspace, self.model_tag)).fetchall()
        if not rows:
            return []
        vector = self._query_vector(text)
        rows = [r for r in rows if r[4] == len(vector)]
        if not rows:
            raise MemoryError("vector_dimension_mismatch")
        if _np is not None:
            matrix = _np.frombuffer(b"".join(r[5] for r in rows), dtype=_np.float32).reshape(len(rows), len(vector))
            scores = (matrix @ _np.asarray(vector, dtype=_np.float32)).tolist()
        else:
            scores = [sum(a * b for a, b in zip(array("f", r[5]), vector)) for r in rows]
        ranked = sorted(((s, r) for s, r in zip(scores, rows) if s >= self.min_score),
                        key=lambda pair: (-pair[0], pair[1][0]))[:limit]
        refs = []
        for _, (pid, workspace, artifact_id, version_id, _, _) in ranked:
            ref = {"workspace": workspace, "artifact_id": artifact_id, "version_id": version_id}
            if self._point(ref) == pid:
                refs.append(ref)
        return refs
