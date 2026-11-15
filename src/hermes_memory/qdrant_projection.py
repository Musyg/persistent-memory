"""Qdrant as a disposable vector projection of the memory, standard library only.

The projection holds vectors and exact refs, never content. It only proposes candidates:
PersistentMemory reads each one again through the authority and applies the same kind,
validity and precondition rules as lexical search. A withdrawn, superseded or invalidated
version is purged at the next synchronization, and if a purge cannot happen (Qdrant down),
the stale vector still cannot bring the version back, because revalidation refuses it.

    from hermes_memory.qdrant_projection import OpenAIEmbeddings, QdrantProjection
    embed = OpenAIEmbeddings("http://127.0.0.1:8000/v1", "nomic-embed-text")
    memory.attach_projection(QdrantProjection(memory, "http://127.0.0.1:6333", embed))
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from .core import Memory, MemoryError, require

__all__ = ["OpenAIEmbeddings", "QdrantREST", "QdrantProjection"]

MAX_EMBED_CHARS = 8000
_SCROLL_PAGE = 1000
_UPSERT_BATCH = 64


def _http_url(url):
    parts = urllib.parse.urlsplit(url or "")
    require(parts.scheme in {"http", "https"} and parts.netloc, "invalid_url")
    return url.rstrip("/")


def _secret(value, env):
    if value is not None:
        return value
    return os.environ.get(env) if env else None


class OpenAIEmbeddings:
    """Any OpenAI-compatible /embeddings endpoint (OpenAI, llama.cpp server, Ollama, vLLM, TEI...)."""

    def __init__(self, base_url, model, *, api_key=None, api_key_env=None, timeout=60, batch=32):
        self.base_url = _http_url(base_url)
        require(type(model) is str and model, "invalid_embedding_model")
        self.model = model
        self.model_id = "openai:" + model
        self._key = _secret(api_key, api_key_env)
        self.timeout = timeout
        self.batch = batch

    def __call__(self, texts):
        vectors = []
        for start in range(0, len(texts), self.batch):
            chunk = [t[:MAX_EMBED_CHARS] for t in texts[start:start + self.batch]]
            body = json.dumps({"model": self.model, "input": chunk}).encode("utf-8")
            request = urllib.request.Request(self.base_url + "/embeddings", data=body, method="POST",
                                             headers={"Content-Type": "application/json"})
            if self._key:
                request.add_header("Authorization", "Bearer " + self._key)
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read())["data"]
            require(len(data) == len(chunk), "embedding_count_mismatch")
            for item in sorted(data, key=lambda d: d["index"]):
                vector = item["embedding"]
                require(type(vector) is list and vector and all(type(x) in (int, float) for x in vector),
                        "invalid_embedding")
                vectors.append(vector)
        return vectors


class QdrantError(OSError):
    pass


class QdrantREST:
    """The few Qdrant REST calls the projection needs."""

    def __init__(self, url, *, api_key=None, api_key_env=None, timeout=10):
        self.url = _http_url(url)
        self._key = _secret(api_key, api_key_env)
        self.timeout = timeout

    def __call__(self, method, path, body=None, allow_404=False):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.url + path, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        if self._key:
            request.add_header("api-key", self._key)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read() or b"{}").get("result")
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and allow_404:
                return None
            raise QdrantError("qdrant_http_%d" % exc.code) from exc


def collection_name(workspace, model_id):
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", workspace)[:40]
    return "persistent-memory-%s-%s" % (safe, hashlib.sha256(model_id.encode("utf-8")).hexdigest()[:8])


class QdrantProjection:
    name = "qdrant"

    def __init__(self, memory, url=None, embed=None, *, collection=None, transport=None, api_key=None,
                 api_key_env=None, min_score=0.5, query_prefix="", document_prefix=""):
        require(embed is not None and callable(embed) and getattr(embed, "model_id", None), "embedder_required")
        self.memory = memory
        self.embed = embed
        self.transport = transport or QdrantREST(url, api_key=api_key, api_key_env=api_key_env)
        self.collection = collection or collection_name(memory.workspace, embed.model_id)
        require(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", self.collection) is not None, "invalid_collection")
        require(type(query_prefix) is str and type(document_prefix) is str, "invalid_prefix")
        # Some models expect a task prefix (e.g. "search_query: " / "search_document: ").
        self.query_prefix, self.document_prefix = query_prefix, document_prefix
        self.model_tag = "embed-" + hashlib.sha256((embed.model_id + "\0" + document_prefix).encode("utf-8")).hexdigest()[:16]
        require(type(min_score) in (int, float) and -1 <= min_score <= 1, "invalid_min_score")
        # Vector search always has a nearest neighbour; below this cosine score a candidate is
        # treated as unrelated. The right value depends on the embedding model.
        self.min_score = float(min_score)
        self.status = "new"

    def _path(self, suffix=""):
        return "/collections/" + self.collection + suffix

    def _filter(self):
        return {"must": [{"key": "workspace", "match": {"value": self.memory.workspace}},
                         {"key": "model", "match": {"value": self.model_tag}}]}

    def _size(self):
        info = self.transport("GET", self._path(), allow_404=True)
        if info is None:
            return None
        vectors = info["config"]["params"]["vectors"]
        return vectors["size"]

    def _existing(self):
        ids, offset = set(), None
        while True:
            body = {"limit": _SCROLL_PAGE, "with_payload": False, "with_vector": False, "filter": self._filter()}
            if offset is not None:
                body["offset"] = offset
            page = self.transport("POST", self._path("/points/scroll"), body)
            ids.update(str(p["id"]) for p in page["points"])
            offset = page.get("next_page_offset")
            if offset is None:
                return ids

    def _current(self):
        """Readable, managed current versions of the workspace, read through the authority."""
        _, rows, _, _ = self.memory.typed.core.snapshot(self.memory.workspace, 5000, 32 * 1024 * 1024)
        wanted = {}
        for ref, envelope in rows:
            if envelope is not None:
                wanted[Memory.point_id(ref, self.model_tag, "0")] = (ref, envelope["text"])
        return wanted

    def sync(self):
        """Purge points that no longer match a readable current version, then add missing ones."""
        wanted = self._current()
        size = self._size()
        stale = sorted(self._existing() - set(wanted)) if size is not None else []
        if stale:
            for start in range(0, len(stale), _SCROLL_PAGE):
                self.transport("POST", self._path("/points/delete?wait=true"),
                               {"points": stale[start:start + _SCROLL_PAGE]})
        present = self._existing() if size is not None else set()
        missing = [pid for pid in sorted(wanted) if pid not in present]
        for start in range(0, len(missing), _UPSERT_BATCH):
            batch = missing[start:start + _UPSERT_BATCH]
            vectors = self.embed([self.document_prefix + wanted[pid][1] for pid in batch])
            require(len(vectors) == len(batch), "embedding_count_mismatch")
            if size is None:
                size = len(vectors[0])
                self.transport("PUT", self._path(), {"vectors": {"size": size, "distance": "Cosine"}})
                self.transport("PUT", self._path("/index?wait=true"),
                               {"field_name": "workspace", "field_schema": "keyword"})
                self.transport("PUT", self._path("/index?wait=true"),
                               {"field_name": "model", "field_schema": "keyword"})
            require(all(len(v) == size for v in vectors), "qdrant_dimension_mismatch")
            points = [{"id": pid, "vector": vector,
                       "payload": {**wanted[pid][0], "model": self.model_tag}}
                      for pid, vector in zip(batch, vectors)]
            self.transport("PUT", self._path("/points?wait=true"), {"points": points})
        return {"collection": self.collection, "purged": len(stale), "added": len(missing),
                "points": len(wanted)}

    def query(self, text, limit):
        """Candidate refs, best first. Never trusted: the caller revalidates every one."""
        size = self._size()
        if size is None:
            return []
        vector = self.embed([self.query_prefix + text])[0]
        require(len(vector) == size, "qdrant_dimension_mismatch")
        result = self.transport("POST", self._path("/points/query"),
                                {"query": vector, "limit": limit, "with_payload": True, "filter": self._filter(),
                                 "score_threshold": self.min_score})
        refs = []
        for point in result["points"]:
            payload = point.get("payload") or {}
            try:
                ref = {"workspace": payload["workspace"], "artifact_id": payload["artifact_id"],
                       "version_id": payload["version_id"]}
            except KeyError:
                continue
            if all(type(v) is str and v for v in ref.values()) and \
                    str(point["id"]) == Memory.point_id(ref, self.model_tag, "0"):
                refs.append(ref)
        return refs
