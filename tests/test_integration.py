"""Real synthetic SQLite/HTTP/CLI transport contracts; no production imports."""
import asyncio
import ast
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import http.client
import json
import os
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from hermes_memory.core import Authority, Memory, MemoryError as CoreError
from hermes_memory.typed_facade import ContractError, Facade, Policy, make_server
from hermes_memory.typed_client import Client
from hermes_memory.typed_memory_tool import execute_tool, with_tool


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.authority = Authority.create(self.root / "authority.sqlite", self.root / "anchor.json")
        self.memory = Memory.create(self.root / "store.sqlite", self.authority)
        self.policy = Policy(enabled=True)
        self.facade = Facade(self.memory, self.root / "index.sqlite", self.policy)
        self.token = "synthetic-private-token-" + "a" * 32
        self.token_file = self.root / "token"
        self.token_file.write_text(self.token, encoding="utf-8")
        self.token_file.chmod(0o600)

    def request(self, **fields):
        return {"schema_version": 1, "policy_id": self.policy.policy_id, **fields}

    def put(self, source="A", text="Copper signal.", metadata=None, previous=None):
        return self.facade.admit_source(self.request(source_id=source, text=text, metadata=metadata or {}, expected_version=previous))["ref"]

    def sync(self):
        return self.facade.sync(self.request())

    @contextmanager
    def server(self, facade=None):
        server = make_server(self.memory, facade or self.facade, token=self.token)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()
            server.server_close()
            worker.join(3)
            self.assertFalse(worker.is_alive())

    def call(self, port, path, payload, token=True, raw=None):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = "Bearer " + self.token
            connection.request("POST", path, raw if raw is not None else json.dumps(payload).encode(), headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def client(self, port):
        return Client("http://127.0.0.1:" + str(port), self.token_file, self.policy.policy_id, self.policy.workspace)

    def test_disabled_no_index_and_legacy_rpc_unchanged(self):
        disabled = Facade(self.memory, self.root / "disabled.sqlite")
        ref = self.memory.register_source("legacy", "L", "Legacy text.")["ref"]
        with self.server(disabled) as port:
            status, result = self.call(port, "/typed/v1/context", self.request(query="x"))
            self.assertEqual((status, result["reason"]), (403, "feature_disabled"))
            status, result = self.call(port, "/rpc", {"op": "read", "ref": ref})
            self.assertEqual((status, result["content"]), (200, "Legacy text."))
        self.assertFalse(disabled.index_path.exists())

    def test_real_http_client_authoritative_context(self):
        ref = self.put(metadata={"aliases": ["SYN-42"]})
        self.sync()
        with self.server() as port:
            result = self.client(port).context({"query": "SYN-42"})
        self.assertEqual(result["items"][0]["ref"], ref)
        self.assertEqual(result["context"], "Copper signal.")

    def test_auth_and_http_admission_forbidden(self):
        with self.assertRaisesRegex(ContractError, "typed_authentication_required"):
            make_server(self.memory, self.facade, token=None)
        with self.server() as port:
            self.assertEqual(self.call(port, "/typed/v1/context", self.request(query="x"), token=False)[0], 401)
            self.assertEqual(self.call(port, "/typed/v1/put", self.request())[0], 405)
            self.assertEqual(self.call(port, "/typed/v1/sync", self.request())[0], 405)

    def test_legacy_same_workspace_cannot_be_adopted(self):
        ref = self.memory.register_source(self.policy.workspace, "legacy", "untyped original")["ref"]
        with self.assertRaisesRegex(ContractError, "legacy_adoption_forbidden"):
            self.put("legacy", previous=ref["version_id"])
        self.assertEqual(self.memory.read(ref)["content"], "untyped original")
        self.put()
        self.sync()
        self.assertEqual(self.facade.context(self.request(query="untyped"))["items"], [])

    def test_policy_and_budget_overrides_rejected(self):
        with self.assertRaisesRegex(ContractError, "dedicated_typed_cohort_required"):
            Policy(enabled=True, workspace="hermes-vault")
        with self.server() as port:
            for fields in ({"workspace": "legacy"}, {"url": "https://invalid.example"}, {"top_k": 6}, {"max_context_chars": True}, {"policy_id": "other"}):
                code, _ = self.call(port, "/typed/v1/context", self.request(query="x", **fields))
                self.assertIn(code, (400, 403))

    def test_unrelated_global_epoch_is_visible(self):
        self.put()
        self.sync()
        self.memory.register_source("unrelated", "U", "background write")
        with self.server() as port:
            result = self.client(port).context({"query": "copper"})
            self.assertEqual(result["status"], "index_stale")
            self.assertEqual(result["context"], "")
            self.sync()
            self.assertEqual(self.client(port).context({"query": "copper"})["status"], "completed")

    def test_cas_update_revoke_and_independent_source(self):
        old = self.put()
        new = self.put(text="Copper revision.", previous=old["version_id"])
        independent = self.put("B", "Independent copper.")
        with self.assertRaises(CoreError):
            self.put(text="late writer", previous=old["version_id"])
        self.memory.revoke_source(self.policy.workspace, "A", "synthetic-revoke")
        self.sync()
        with self.server() as port:
            result = self.client(port).context({"query": "copper"})
        self.assertEqual([item["ref"] for item in result["items"]], [independent])
        self.assertFalse(self.memory.read(old)["allowed"])
        self.assertFalse(self.memory.read(new)["allowed"])

    def test_corrupt_projection_body_is_not_returned(self):
        self.put()
        self.sync()
        with sqlite3.connect(self.facade.index_path) as connection:
            connection.execute("UPDATE lexical SET text='forged poison'")
        with self.server() as port:
            result = self.client(port).context({"query": "poison"})
        self.assertEqual(result["context"], "Copper signal.")

    def test_missing_anchor_is_unavailable_not_empty_success(self):
        self.put()
        self.sync()
        self.authority.anchor_path.unlink()
        with self.server() as port:
            result = self.client(port).context({"query": "copper"})
        self.assertEqual(result["status"], "unavailable")

    def test_sync_limit_keeps_previous_index(self):
        self.put()
        self.sync()
        before = hashlib.sha256(self.facade.index_path.read_bytes()).hexdigest()
        self.put("B", "new copper")
        limited = Facade(self.memory, self.facade.index_path, replace(self.policy, max_documents=1))
        with self.assertRaisesRegex(ValueError, "sync_document_limit"):
            limited.sync(self.request())
        self.assertEqual(hashlib.sha256(self.facade.index_path.read_bytes()).hexdigest(), before)

    def test_input_json_duplicates_and_size_refuse(self):
        with self.server() as port:
            self.assertEqual(self.call(port, "/typed/v1/context", {}, raw=b'{"query":"a","query":"b"}')[0], 400)
            self.assertEqual(self.call(port, "/typed/v1/context", {}, raw=b" " * 16385)[0], 413)

    def test_parallel_admission_is_bounded(self):
        self.put()
        self.sync()
        self.facade._queries.acquire()
        self.facade._queries.acquire()
        try:
            with self.server() as port:
                code, result = self.call(port, "/typed/v1/context", self.request(query="copper"))
            self.assertEqual((code, result["reason"]), (429, "busy"))
        finally:
            self.facade._queries.release()
            self.facade._queries.release()

    def test_real_readonly_tool_and_disabled_schema(self):
        self.put()
        self.sync()
        with patch.dict(os.environ, {"HERMES_TYPED_MEMORY_ENABLED": "0"}):
            self.assertEqual(with_tool([]), [])
            self.assertFalse(asyncio.run(execute_tool({"query": "copper"}))["success"])
        with self.server() as port, patch.dict(os.environ, {"HERMES_TYPED_MEMORY_ENABLED": "1"}):
            self.assertEqual(len(with_tool([])), 1)
            self.assertEqual(with_tool([], "phantom"), [])
            result = asyncio.run(execute_tool({"query": "copper"}, client=self.client(port)))
            self.assertTrue(result["success"])
            bad = asyncio.run(execute_tool({"query": "copper", "workspace": "legacy"}, client=self.client(port)))
            self.assertFalse(bad["success"])

    def test_real_administrative_cli_admits_then_syncs(self):
        config = self.root / "config.json"
        config.write_text('{"enabled":true}', encoding="utf-8")
        request = self.root / "request.json"
        request.write_text(json.dumps(self.request(source_id="CLI", text="Synthetic cli copper", metadata={}, expected_version=None)), encoding="utf-8")
        base = [sys.executable, "-m", "hermes_memory.typed_admin", "--authority", str(self.authority.path), "--anchor", str(self.authority.anchor_path), "--store", str(self.memory.path), "--index", str(self.facade.index_path), "--config", str(config)]
        for operation in (["put", "--request", str(request)], ["sync"]):
            result = subprocess.run(base + operation, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
        with self.server() as port:
            self.assertEqual(self.client(port).context({"query": "CLI"})["context"], "Synthetic cli copper")

    def test_restart_reopen_and_identical_retry_converge(self):
        ref = self.put()
        self.assertEqual(self.put(), ref)
        self.sync()
        reopened = Facade(Memory.open(self.memory.path, Authority.open(self.authority.path, self.authority.anchor_path)), self.facade.index_path, self.policy)
        with self.server(reopened) as port:
            self.assertEqual(self.client(port).context({"query": "copper"})["items"][0]["ref"], ref)

    def test_no_automatic_sync_or_success_on_programming_error(self):
        self.put()
        self.sync()
        with patch.object(self.facade.typed(), "search", side_effect=ValueError("synthetic bug")), self.server() as port:
            result = self.client(port).context({"query": "copper"})
        self.assertEqual(result["status"], "error")


    def test_revocation_after_validation_discards_http_context(self):
        self.put()
        self.sync()
        original = self.memory.validate
        def changed(refs):
            result = original(refs)
            self.memory.revoke_source(self.policy.workspace, "A", "synthetic-mid-read")
            return result
        with patch.object(self.memory, "validate", changed), self.server() as port:
            result = self.client(port).context({"query": "copper"})
        self.assertEqual(result["status"], "epoch_changed")
        self.assertEqual(result["context"], "")

    def test_old_content_snapshot_with_current_authority_stays_revoked(self):
        self.put()
        independent = self.put("B", "Independent copper")
        snapshot = self.root / "old-content.sqlite"
        shutil.copyfile(self.memory.path, snapshot)
        self.memory.revoke_source(self.policy.workspace, "A", "synthetic-restore")
        shutil.copyfile(snapshot, self.memory.path)
        self.sync()
        with self.server() as port:
            result = self.client(port).context({"query": "copper"})
        self.assertEqual([item["ref"] for item in result["items"]], [independent])

    def test_private_token_permissions_and_unknown_http_backend_preserve_failure(self):
        self.token_file.chmod(0o644)
        with self.server() as port:
            with self.assertRaisesRegex(ContractError, "private_token"):
                self.client(port).context({"query": "copper"})
        self.token_file.chmod(0o600)
        unavailable = Client("http://127.0.0.1:1", self.token_file, self.policy.policy_id, self.policy.workspace, timeout=0.1)
        self.assertEqual(unavailable.context({"query": "copper"})["status"], "unavailable")

    def test_cancellation_while_worker_queued_does_not_leak_slot(self):
        from hermes_memory import typed_memory_tool
        gate, completed = threading.Event(), threading.Event()
        class CancellationProbe:
            def context(self, arguments):
                completed.set()
                return {"status": "completed"}
        async def scenario():
            loop = asyncio.get_running_loop()
            pool = ThreadPoolExecutor(max_workers=1)
            loop.set_default_executor(pool)
            occupied = loop.run_in_executor(None, gate.wait)
            try:
                pending = asyncio.create_task(execute_tool({"query": "synthetic"}, client=CancellationProbe()))
                await asyncio.sleep(.05)
                pending.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await pending
                self.assertFalse(completed.is_set())
                gate.set()
                await occupied
                for _ in range(100):
                    if completed.is_set():
                        break
                    await asyncio.sleep(.01)
                self.assertTrue(completed.is_set())
                first = typed_memory_tool._calls.acquire(blocking=False)
                second = typed_memory_tool._calls.acquire(blocking=False)
                try:
                    self.assertTrue(first and second)
                finally:
                    if first:
                        typed_memory_tool._calls.release()
                    if second:
                        typed_memory_tool._calls.release()
            finally:
                gate.set()
        with patch.dict(os.environ, {"HERMES_TYPED_MEMORY_ENABLED": "1"}):
            asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main(verbosity=2)
