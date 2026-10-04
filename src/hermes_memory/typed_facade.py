"""Opt-in HTTP reads over one existing authority; explicit local admission only."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from pathlib import Path
import sqlite3
import threading

from hermes_memory.interfaces import make_server as make_core_server
from hermes_memory.core import MemoryError as CoreError
from .typed_memory import TypedMemory, RetrievalError, canonical, decode, metadata
from .typed_protocol import ContractError, R3_SHA, require, strict_json

PREFIX = "/typed/v1/"


@dataclass(frozen=True)
class Policy:
    enabled: bool = False
    policy_id: str = "typed-pilot-v1"
    workspace: str = "hermes-typed-pilot-v1"
    top_k: int = 5
    max_context_chars: int = 2000
    candidate_limit: int = 100
    max_documents: int = 100
    max_content_bytes: int = 4194304
    concurrent_queries: int = 2

    def __post_init__(self):
        require(type(self.enabled) is bool, "invalid_enabled")
        for value in (self.policy_id, self.workspace):
            require(type(value) is str and 0 < len(value) <= 128 and all(c.isalnum() or c in "-_." for c in value), "invalid_policy_name")
        require(self.workspace.startswith("hermes-typed-") and len(self.workspace) > len("hermes-typed-"), "dedicated_typed_cohort_required")
        bounds = ((self.top_k, 1, 64), (self.max_context_chars, 0, 64000), (self.candidate_limit, self.top_k, 128), (self.max_documents, 1, 5000), (self.max_content_bytes, 1, 134217728), (self.concurrent_queries, 1, 4))
        require(all(type(value) is int and lo <= value <= hi for value, lo, hi in bounds), "invalid_policy_limit")


class Facade:
    def __init__(self, memory, index_path, policy=None):
        self.memory = memory
        self.policy = policy or Policy()
        self.index_path = Path(index_path).absolute()
        self._typed = None
        self._initialize = threading.Lock()
        self._queries = threading.BoundedSemaphore(self.policy.concurrent_queries)
        self._maintenance = threading.Lock()
        # No typed constructor, index file or worker when disabled.

    def check(self, request, fields):
        require(self.policy.enabled, "feature_disabled", 403)
        require(type(request) is dict and set(request) <= fields and {"schema_version", "policy_id"} <= set(request), "invalid_request")
        require(type(request["schema_version"]) is int and request["schema_version"] == 1, "invalid_schema_version")
        require(request["policy_id"] == self.policy.policy_id, "policy_not_admitted", 403)

    def typed(self, create=False):
        with self._initialize:
            if self._typed is None:
                require(create or self.index_path.is_file(), "index_stale", 409)
                from . import typed_memory
                require(hashlib.sha256(Path(typed_memory.__file__).read_bytes()).hexdigest() == R3_SHA, "library_revision_mismatch", 503)
                try:
                    self._typed = TypedMemory(self.memory, self.index_path)
                except RetrievalError as exc:
                    if str(exc) in {"index_backend_unavailable", "index_schema_mismatch", "unsupported_core_version"}:
                        raise ContractError("index_or_library_unavailable", 503) from exc
                    raise
            return self._typed

    @contextmanager
    def admitted(self, guard):
        require(guard.acquire(blocking=False), "busy", 429)
        try:
            yield
        finally:
            guard.release()

    def context(self, request):
        self.check(request, {"schema_version", "policy_id", "query", "as_of", "conditions", "evidence_kinds", "top_k", "max_context_chars"})
        require("query" in request, "query_required")
        top = request.get("top_k", self.policy.top_k)
        budget = request.get("max_context_chars", self.policy.max_context_chars)
        require(type(top) is int and 1 <= top <= self.policy.top_k, "top_k_exceeds_policy")
        require(type(budget) is int and 0 <= budget <= self.policy.max_context_chars, "context_budget_exceeds_policy")
        with self.admitted(self._queries):
            result = self.typed().search(self.policy.workspace, request["query"], as_of=request.get("as_of"), conditions=request.get("conditions"), evidence_kinds=request.get("evidence_kinds"), top_k=top, max_context_chars=budget, candidate_limit=self.policy.candidate_limit)
        return {**result, "schema_version": 1, "policy_id": self.policy.policy_id, "library_sha256": R3_SHA}

    def status(self, request):
        self.check(request, {"schema_version", "policy_id"})
        cp = self.memory.checkpoint()
        readiness = "missing"
        if self.index_path.is_file():
            with sqlite3.connect(self.index_path.as_uri() + "?mode=ro", uri=True) as connection:
                row = connection.execute("SELECT generation,epoch FROM checkpoints WHERE workspace=?", (self.policy.workspace,)).fetchone()
            readiness = "ready" if row and (row[0], row[1]) == (cp["generation"], cp["epoch"]) else "stale"
        return {"schema_version": 1, "policy_id": self.policy.policy_id, "status": "completed", "authority": "ready", "index": readiness, "readiness_is_point_in_time": True}

    def admit_source(self, request):
        """Local admin API; intentionally not routed by the HTTP facade."""
        self.check(request, {"schema_version", "policy_id", "source_id", "text", "metadata", "expected_version"})
        require({"source_id", "text", "metadata", "expected_version"} <= set(request), "admission_fields_required")
        require(len(canonical(request).encode("utf-8")) <= 262144, "body_limit", 413)
        with self.admitted(self._maintenance):
            # Never upgrade a legacy current head, even in the configured workspace.
            require(type(request["source_id"]) is str, "invalid_source_id")
            with self.memory.authority.transaction() as connection:
                head = connection.execute("SELECT version_id FROM heads WHERE workspace=? AND artifact_id=?", (self.policy.workspace, request["source_id"])).fetchone()
            if head is not None:
                previous = {"workspace": self.policy.workspace, "artifact_id": request["source_id"], "version_id": head[0]}
                decision = self.memory.read(previous)
                require(decision["allowed"], "source_ineligible", 409)
                require(decode(decision["content"]) is not None, "legacy_adoption_forbidden", 409)
            require(request["expected_version"] is None or type(request["expected_version"]) is str, "invalid_expected_version")
            normalized = metadata(request["metadata"])
            result = self.typed(create=True).put(self.policy.workspace, request["source_id"], request["text"], normalized, expected_version=request["expected_version"])
        return {"schema_version": 1, "policy_id": self.policy.policy_id, "committed": True, "indexed": False, **result}

    def sync(self, request):
        """Explicit bounded admin operation; no query-time automatic refresh."""
        self.check(request, {"schema_version", "policy_id"})
        with self.admitted(self._maintenance):
            result = self.typed(create=True).sync(self.policy.workspace, max_documents=self.policy.max_documents, max_content_bytes=self.policy.max_content_bytes)
        return {"schema_version": 1, "policy_id": self.policy.policy_id, **result}


def make_server(memory, facade, host="127.0.0.1", port=0, token=None):
    require(not facade.policy.enabled or type(token) is str and len(token) >= 32, "typed_authentication_required", 403)
    server = make_core_server(memory, host, port, token)
    original = server.RequestHandlerClass

    class Handler(original):
        def do_POST(self):
            if not self.path.startswith(PREFIX):
                return super().do_POST()
            if not self.authorized():
                return self.answer(401, {"error": "unauthorized"})
            try:
                require(facade.policy.enabled, "feature_disabled", 403)
                require(self.path in {PREFIX + "context", PREFIX + "status"}, "administrative_or_unknown_route", 405)
                require(self.headers.get("Transfer-Encoding") is None, "transfer_encoding_unsupported")
                lengths = self.headers.get_all("Content-Length", [])
                require(len(lengths) == 1 and lengths[0].isdigit(), "invalid_body_size")
                length = int(lengths[0])
                require(0 < length <= 16384, "body_limit", 413)
                raw = self.rfile.read(length)
                require(len(raw) == length, "truncated_body")
                request = strict_json(raw)
                result = facade.context(request) if self.path.endswith("/context") else facade.status(request)
                require(len(canonical(result).encode("utf-8")) <= 262144, "response_limit", 503)
                status = {"index_stale": 409, "epoch_changed": 409, "unavailable": 503}.get(result["status"], 200)
                return self.answer(status, result)
            except ContractError as exc:
                return self.answer(exc.status, {"status": "unavailable" if exc.status == 503 else "refused", "reason": exc.reason})
            except RetrievalError:
                return self.answer(400, {"status": "refused", "reason": "invalid_typed_request"})
            except (OSError, sqlite3.Error, CoreError):
                return self.answer(503, {"status": "unavailable", "reason": "authority_or_store_unavailable"})
            except Exception:
                return self.answer(500, {"status": "error", "reason": "internal_error"})

    server.RequestHandlerClass = Handler
    return server
