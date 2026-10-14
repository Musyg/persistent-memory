"""R3 adapts one R2 assertion to its explicit unavailable response contract.

The original 14-test file remains frozen; all other tests are inherited intact.
"""
import sqlite3
import unittest
import typed_review_base as base


class IndependentR3(base.IndependentChecks):
    def test_foreign_reference_in_projection_is_refused(self):
        self.put()
        foreign = self.put("foreign", "foreign synthetic material", workspace="other")
        self.typed.sync("demo")
        with sqlite3.connect(self.index) as db:
            db.execute("UPDATE documents SET ref=?", (base.canonical(foreign),))
        result = self.typed.search("demo", "copper")
        self.assert_empty_status(result, "unavailable")
        self.assertEqual(result["reason"], "projection_scope_mismatch")

        # Fixed workspace/token boundary, not human authentication or voice recognition.
        import http.client
        import json
        import threading
        from hermes_memory.typed_facade import Facade, Policy, make_server
        from hermes_memory.typed_client import Client
        from hermes_memory.typed_memory import render_context_item
        from hermes_memory.typed_protocol import ContractError

        for value in (1, "true", None):
            with self.subTest(policy_flag=value), self.assertRaises(ContractError):
                Policy(render_source_references=value)
            with self.subTest(host_flag=value), self.assertRaises(ContractError):
                make_server(self.memory, Facade(self.memory, self.directory / "invalid.db"), typed_only=value)
            with self.subTest(client_flag=value), self.assertRaises(ContractError):
                Client("http://127.0.0.1", "unused", "test", "hermes-typed-A", render_source_references=value)
        facades = [Facade(self.memory, self.directory / ("boundary-" + key + ".db"),
                          Policy(enabled=True, policy_id="boundary-" + key,
                                 workspace="hermes-typed-" + key,
                                 render_source_references=True)) for key in ("A", "B")]
        refs = [[], []]
        for index, facade in enumerate(facades):
            for identity, text in [("shared-id", "copper brief " + ("A", "B")[index])] + (
                    [("second-id", "copper second A")] if index == 0 else []):
                refs[index].append(facade.admit_source({"schema_version": 1,
                    "policy_id": facade.policy.policy_id, "source_id": identity,
                    "text": text, "metadata": {}, "expected_version": None})["ref"])
        for facade in facades:
            facade.sync({"schema_version": 1, "policy_id": facade.policy.policy_id})
        tokens = ("A" * 32, "B" * 32)
        token_paths = []
        for index, token in enumerate(tokens):
            token_path = self.directory / ("token-" + str(index))
            token_path.write_text(token); token_path.chmod(0o600); token_paths.append(token_path)
        servers, threads = [], []
        try:
            for facade, token in zip(facades, tokens):
                server = make_server(self.memory, facade, token=token, typed_only=True)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start(); servers.append(server); threads.append(thread)

            def call(server, method, path, token, body=None):
                connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
                headers = {} if token is None else {"Authorization": "Bearer " + token}
                try:
                    connection.request(method, path, None if body is None else json.dumps(body), headers)
                    response = connection.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    connection.close()

            for index, (server, facade, token) in enumerate(zip(servers, facades, tokens)):
                request = {"schema_version": 1, "policy_id": facade.policy.policy_id, "query": "copper"}
                code, result = call(server, "POST", "/typed/v1/context", token, request)
                self.assertEqual(code, 200)
                self.assertEqual({base.canonical(item["ref"]) for item in result["items"]},
                                 {base.canonical(ref) for ref in refs[index]})
                expected = "\n\n".join(render_context_item(item["text"], item["ref"], True) for item in result["items"])
                self.assertEqual(result["context"], expected)
                for ref in refs[1-index]:
                    self.assertNotIn(json.dumps(ref, ensure_ascii=True, sort_keys=True, separators=(",", ":")), result["context"])
                endpoint = "http://127.0.0.1:" + str(server.server_address[1])
                client = Client(endpoint, token_paths[index], facade.policy.policy_id,
                                facade.policy.workspace, render_source_references=True)
                self.assertEqual(client.context({"query": "copper"})["context"], expected)
                plain_client = Client(endpoint, token_paths[index], facade.policy.policy_id, facade.policy.workspace)
                with self.assertRaisesRegex(ContractError, "response_context_binding"):
                    plain_client.context({"query": "copper"})
                if index == 0:
                    self.assertEqual(client.context({"query": "copper", "max_context_chars": len(expected)})["context"], expected)
                    short = client.context({"query": "copper", "max_context_chars": len(expected)-1})
                    self.assertLess(len(short["items"]), 2)
                    self.assertLessEqual(len(short["context"]), len(expected)-1)
                for supplied in (None, tokens[1-index]):
                    self.assertEqual(call(server, "POST", "/typed/v1/context", supplied, request)[0], 401)
                for extra in ({"workspace": facades[1-index].policy.workspace}, {"render_source_references": False}):
                    self.assertEqual(call(server, "POST", "/typed/v1/context", token, {**request, **extra})[0], 400)
                before = self.memory.checkpoint()
                for path in ("/rpc", "/validate", "/health", "/unknown", "/typed", "/typed/v1/../rpc"):
                    with self.subTest(host=index, blocked=path):
                        self.assertEqual(call(server, "GET", path, token)[0], 405)
                        self.assertEqual(call(server, "POST", path, token, {"op": "checkpoint"})[0], 405)
                self.assertEqual(call(server, "GET", "/typed/v1/context", token)[0], 405)
                self.assertEqual(self.memory.checkpoint(), before)
            plain = Facade(self.memory, self.directory / "plain-default.db",
                           Policy(enabled=True, policy_id="plain-default", workspace="hermes-typed-A"))
            plain.sync({"schema_version": 1, "policy_id": "plain-default"})
            legacy = make_server(self.memory, plain, token=tokens[0])
            legacy_thread = threading.Thread(target=legacy.serve_forever, daemon=True)
            legacy_thread.start(); servers.append(legacy); threads.append(legacy_thread)
            self.assertEqual(call(legacy, "GET", "/health", tokens[0])[0], 200)
            self.assertEqual(call(legacy, "POST", "/rpc", tokens[0], {"op": "checkpoint"})[0], 200)
            self.assertEqual(call(legacy, "POST", "/validate", tokens[0], {"refs": []})[0], 200)
            endpoint = "http://127.0.0.1:" + str(legacy.server_address[1])
            plain_client = Client(endpoint, token_paths[0], "plain-default", "hermes-typed-A")
            plain_result = plain_client.context({"query": "copper"})
            self.assertEqual(plain_result["context"], "\n\n".join(item["text"] for item in plain_result["items"]))
            refs_client = Client(endpoint, token_paths[0], "plain-default", "hermes-typed-A", render_source_references=True)
            with self.assertRaisesRegex(ContractError, "response_context_binding"):
                refs_client.context({"query": "copper"})
        finally:
            for server in servers:
                server.shutdown(); server.server_close()
            for thread in threads:
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main(verbosity=2)
