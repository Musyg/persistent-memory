"""Independent synthetic HTTP contract tests, pinned slice1-r2; Linux only.

Assertions express the published contract, including suspected defects. A failing
test must remain a finding, never an expectedFailure or a successful empty read.
"""
import asyncio
from contextlib import contextmanager
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from hermes_memory.core import Authority, Memory
from hermes_memory.typed_facade import Facade, Policy, make_server
from hermes_memory.typed_client import Client
from hermes_memory.typed_protocol import ContractError, canonical
from hermes_memory import typed_memory_tool


class IndependentIntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.authority = Authority.create(self.root / "authority.sqlite", self.root / "anchor.json")
        self.memory = Memory.create(self.root / "store.sqlite", self.authority)
        self.policy = Policy(enabled=True)
        self.facade = Facade(self.memory, self.root / "index.sqlite", self.policy)
        self.token = "synthetic-review-token-" + "b" * 32
        self.token_file = self.root / "token"
        self.token_file.write_text(self.token, encoding="utf-8")
        self.token_file.chmod(0o600)

    def request(self, **values):
        return {"schema_version": 1, "policy_id": self.policy.policy_id, **values}

    def prepared(self, text="Copper signal."):
        self.ref = self.facade.admit_source(self.request(source_id="A", text=text, metadata={}, expected_version=None))["ref"]
        self.facade.sync(self.request())
        return self.facade.context(self.request(query="copper"))

    @contextmanager
    def running(self, server):
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        thread.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)
            self.assertFalse(thread.is_alive())

    @contextmanager
    def wire(self, payload, code=200, delayed=False, truncated=False, entered=None, release=None):
        """Real loopback peer emitting fixed synthetic bytes; no network mocks."""
        raw = payload if isinstance(payload, bytes) else canonical(payload).encode("utf-8")
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(code)
                self.send_header("Content-Length", str(len(raw) + (20 if truncated else 0)))
                self.end_headers()
                self.wfile.flush()
                if entered is not None:
                    entered.set()
                if delayed:
                    threading.Event().wait(.2)
                if release is not None:
                    release.wait(2)
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        with self.running(ThreadingHTTPServer(("127.0.0.1", 0), Handler)) as port:
            yield port

    def client(self, port, timeout=1):
        return Client("http://127.0.0.1:" + str(port), self.token_file, self.policy.policy_id, self.policy.workspace, timeout)

    def call(self, port, path, payload=None, authenticated=True):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        try:
            headers = {"Authorization": "Bearer " + self.token} if authenticated else {}
            connection.request("GET" if payload is None else "POST", path, None if payload is None else canonical(payload).encode(), headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_real_valid_response_preserves_exact_provenance(self):
        expected = self.prepared()
        with self.running(make_server(self.memory, self.facade, token=self.token)) as port:
            self.assertEqual(self.client(port).context({"query": "copper"}), expected)

    def test_duplicate_response_json_is_rejected(self):
        with self.wire(b'{"status":"completed","status":"completed"}') as port:
            with self.assertRaises(ContractError):
                self.client(port).context({"query": "copper"})

    def test_response_byte_cap_is_enforced_before_parse(self):
        with self.wire(b" " * 262145) as port:
            with self.assertRaisesRegex(ContractError, "response_limit"):
                self.client(port).context({"query": "copper"})

    def test_response_cross_workspace_ref_rejected(self):
        result = self.prepared()
        result["items"][0]["ref"]["workspace"] = "other-workspace"
        with self.wire(result) as port:
            with self.assertRaisesRegex(ContractError, "response_ref_scope"):
                self.client(port).context({"query": "copper"})

    def test_unicode_context_budget_rejected_without_truncating_provenance(self):
        result = self.prepared("Copper 🧭🧭")
        with self.wire(result) as port:
            with self.assertRaisesRegex(ContractError, "response_context_binding"):
                self.client(port).context({"query": "copper", "max_context_chars": len(result["context"]) - 1})

    def test_failure_content_is_never_forwarded(self):
        with self.wire({"status": "unavailable", "items": [], "context": "synthetic forbidden output"}, 503) as port:
            with self.assertRaisesRegex(ContractError, "failure_content_forbidden"):
                self.client(port).context({"query": "copper"})

    def test_conflict_reason_is_preserved(self):
        with self.wire({"status": "index_stale", "reason": "synthetic_stale", "items": [], "context": ""}, 409) as port:
            result = self.client(port).context({"query": "copper"})
        self.assertEqual((result["status"], result["reason"], result["context_empty"]), ("index_stale", "synthetic_stale", True))

    def test_completed_response_requires_epoch(self):
        result = self.prepared()
        del result["epoch"]
        with self.wire(result) as port:
            with self.assertRaises(ContractError):
                self.client(port).context({"query": "copper"})

    def test_completed_response_requires_coverage(self):
        result = self.prepared()
        del result["coverage"]
        with self.wire(result) as port:
            with self.assertRaises(ContractError):
                self.client(port).context({"query": "copper"})

    def test_completed_response_uses_top_level_allowlist(self):
        result = self.prepared()
        result["unexpected_field"] = "synthetic undeclared peer field"
        with self.wire(result) as port:
            with self.assertRaises(ContractError):
                self.client(port).context({"query": "copper"})

    def test_cold_corrupt_index_is_dependency_unavailable(self):
        self.prepared()
        self.facade.index_path.write_bytes(b"synthetic invalid sqlite file")
        cold = Facade(self.memory, self.facade.index_path, self.policy)
        with self.running(make_server(self.memory, cold, token=self.token)) as port:
            code, result = self.call(port, "/typed/v1/context", self.request(query="copper"))
        self.assertEqual(code, 503, result)
        self.assertIn(result["status"], ("unavailable", "refused"))
        self.assertFalse(result.get("context"))

    def test_typed_enabled_requires_auth_even_on_loopback(self):
        self.prepared()
        try:
            server = make_server(self.memory, self.facade, token=None)
        except (ContractError, ValueError):
            return  # Rejecting invalid enabled configuration at construction is valid.
        with self.running(server) as port:
            code, result = self.call(port, "/typed/v1/context", self.request(query="copper"), authenticated=False)
        self.assertIn(code, (401, 403), result)
        self.assertFalse(result.get("context"))

    def test_disabled_legacy_health_validate_and_auth_remain_compatible(self):
        ref = self.memory.register_source("legacy", "L", "Synthetic legacy text")["ref"]
        disabled = Facade(self.memory, self.root / "disabled.sqlite")
        with self.running(make_server(self.memory, disabled, token=self.token)) as port:
            self.assertEqual(self.call(port, "/health")[0], 200)
            self.assertEqual(self.call(port, "/validate", {"refs": [ref]})[1], self.memory.validate([ref]))
            for path, payload in (("/health", None), ("/validate", {"refs": [ref]}), ("/rpc", {"op": "read", "ref": ref})):
                self.assertEqual(self.call(port, path, payload, authenticated=False)[0], 401)
        self.assertFalse(disabled.index_path.exists())

    def test_body_read_timeout_has_transport_provenance(self):
        expected = self.prepared()
        with self.wire(expected, delayed=True) as port:
            result = self.client(port, timeout=.05).context({"query": "copper"})
        self.assertEqual((result["status"], result["reason"]), ("unavailable", "transport_unavailable"))
        self.assertEqual(result["context"], "")

    def test_tool_body_read_timeout_keeps_transport_reason(self):
        expected = self.prepared()
        with self.wire(expected, delayed=True) as port, patch.dict(os.environ, {"HERMES_TYPED_MEMORY_ENABLED": "1"}):
            result = asyncio.run(typed_memory_tool.execute_tool({"query": "copper"}, client=self.client(port, timeout=.05)))
        self.assertFalse(result["success"])
        self.assertEqual(result["result"]["reason"], "transport_unavailable")

    def test_running_http_cancellation_retains_then_releases_slot(self):
        expected = self.prepared()
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        slots = threading.BoundedSemaphore(2)
        async def scenario(port):
            actual = self.client(port)
            class ObservedClient:
                def context(self, arguments):
                    try:
                        return actual.context(arguments)
                    finally:
                        finished.set()
            pending = asyncio.create_task(typed_memory_tool.execute_tool({"query": "copper"}, client=ObservedClient()))
            try:
                for _ in range(100):
                    if entered.is_set():
                        break
                    await asyncio.sleep(.01)
                self.assertTrue(entered.is_set())
                pending.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await pending
                second = slots.acquire(blocking=False)
                self.assertTrue(second)
                try:
                    busy = await typed_memory_tool.execute_tool({"query": "copper"}, client=actual)
                    self.assertEqual(busy["result"]["reason"], "busy")
                finally:
                    if second:
                        slots.release()
                release.set()
                for _ in range(100):
                    if finished.is_set():
                        break
                    await asyncio.sleep(.01)
                self.assertTrue(finished.is_set())
                await asyncio.sleep(.01)  # work.finally runs immediately after context.finally.
                first, second = slots.acquire(False), slots.acquire(False)
                try:
                    self.assertTrue(first and second)
                finally:
                    if first:
                        slots.release()
                    if second:
                        slots.release()
            finally:
                release.set()
                if not pending.done():
                    pending.cancel()
        with self.wire(expected, entered=entered, release=release) as port, patch.dict(os.environ, {"HERMES_TYPED_MEMORY_ENABLED": "1"}), patch.object(typed_memory_tool, "_calls", slots):
            asyncio.run(scenario(port))


if __name__ == "__main__":
    unittest.main(verbosity=2)
