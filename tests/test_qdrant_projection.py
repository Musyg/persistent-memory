"""The Qdrant projection: candidates only, never content, purged on withdrawal, never trusted."""
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from hermes_memory.core import Memory, MemoryError
from hermes_memory.persistent import PersistentMemory
from hermes_memory.qdrant_projection import OpenAIEmbeddings, QdrantError, QdrantProjection, QdrantREST
from qdrant_fake import FakeQdrant, HashEmbedder

FIREWALL = "Pour Orion-Test, ouvrir le port 9300 sur le pare-feu."


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.memory = PersistentMemory(Path(self._tmp.name) / "store", "ws", create=True)
        self.qdrant, self.embed = FakeQdrant(), HashEmbedder()
        self.projection = QdrantProjection(self.memory, embed=self.embed, transport=self.qdrant)
        self.assertEqual(self.memory.attach_projection(self.projection), "ok")

    def tearDown(self):
        self._tmp.cleanup()

    def points(self):
        collection = self.qdrant.collections.get(self.projection.collection)
        return collection["points"] if collection else {}

    def ids(self, query, **kwargs):
        return [i["artifact_id"] for i in self.memory.search(query, **kwargs)["items"]]


class Projection(Base):
    def test_semantic_candidate_found_where_lexical_misses(self):
        self.memory.remember(FIREWALL, source_id="fw")
        self.memory.remember("La couleur de la marque est le vert sapin.", source_id="color")
        lexical_only = PersistentMemory(self.memory.root, "ws")
        self.assertEqual(lexical_only.search("firewall")["items"], [])
        result = self.memory.search("firewall")
        self.assertEqual([i["artifact_id"] for i in result["items"]], ["fw"])
        self.assertEqual(result["semantic"]["status"], "ok")

    def test_points_hold_refs_not_content(self):
        stored = self.memory.remember(FIREWALL, source_id="fw")
        (pid, point), = self.points().items()
        self.assertEqual(set(point["payload"]), {"workspace", "artifact_id", "version_id", "model"})
        self.assertNotIn("pare-feu", json.dumps(point["payload"]))
        self.assertEqual(pid, Memory.point_id(stored["ref"], self.projection.model_tag, "0"))

    def test_withdrawal_and_correction_purge_points(self):
        src = self.memory.remember(FIREWALL, source_id="fw")
        self.memory.derive("Checklist: pare-feu 9300.", parents=[src["ref"]], artifact_id="child")
        self.assertEqual(len(self.points()), 2)
        self.memory.correct("fw", "Pour Orion-Test, ouvrir le port 9400 sur le pare-feu.",
                            expected_version=src["ref"]["version_id"])
        self.assertEqual({p["payload"]["artifact_id"] for p in self.points().values()}, {"fw"})
        self.memory.withdraw("fw", "obsolete")
        self.assertEqual(self.points(), {})

    def test_stale_vector_cannot_bring_back_a_withdrawn_version(self):
        self.memory.remember(FIREWALL, source_id="fw")
        self.qdrant.down = True
        self.memory.withdraw("fw", "obsolete")  # the authority records it even with Qdrant down
        self.assertEqual(self.projection.status, "unavailable")
        self.qdrant.down = False
        self.assertEqual(len(self.points()), 1)  # the purge has not happened yet
        result = self.memory.search("firewall")
        self.assertEqual(result["items"], [])
        self.assertIn("source_revoked", {e["reason"] for e in result["exclusions"]})
        self.memory.remember("Autre fait.", source_id="other")
        self.assertEqual({p["payload"]["artifact_id"] for p in self.points().values()}, {"other"})

    def test_qdrant_down_at_query_falls_back_to_lexical(self):
        self.memory.remember(FIREWALL, source_id="fw")
        self.qdrant.down = True
        result = self.memory.search("Orion-Test pare-feu")
        self.assertEqual([i["artifact_id"] for i in result["items"]], ["fw"])
        self.assertEqual(result["semantic"]["status"], "unavailable")

    def test_tampered_payload_is_ignored(self):
        self.memory.remember(FIREWALL, source_id="fw")
        secret = self.memory.remember("Code interne 4242.", source_id="secret")
        point = next(iter(self.points().values()))
        point["payload"]["artifact_id"] = "secret"
        point["payload"]["version_id"] = secret["ref"]["version_id"]
        self.assertEqual(self.projection.query("firewall", 10), [])

    def test_other_workspaces_are_not_returned(self):
        other = PersistentMemory(self.memory.root, "other")
        other.attach_projection(QdrantProjection(other, embed=self.embed, transport=self.qdrant,
                                                 collection=self.projection.collection))
        other.remember(FIREWALL, source_id="theirs")
        self.assertEqual(self.ids("firewall"), [])
        self.assertEqual(len(self.points()), 1)

    def test_sync_is_incremental_and_skips_lesson_parents(self):
        self.memory.learn({"task": "export"}, {"success": False}, "Exporter avec BOM.", lesson_id="lesson")
        self.assertEqual({p["payload"]["artifact_id"] for p in self.points().values()}, {"lesson"})
        calls = self.embed.calls
        self.assertEqual(self.projection.sync()["added"], 0)
        self.assertEqual(self.embed.calls, calls)

    def test_filters_apply_to_semantic_candidates(self):
        self.memory.remember(FIREWALL, source_id="old", valid_until="2001-01-01T00:00:00Z")
        self.memory.remember("Firewall staging: ouvrir 9500.", source_id="prod", preconditions={"env": "prod"},
                             kind="procedure")
        self.assertEqual(self.ids("pare-feu"), [])
        self.assertEqual(self.ids("pare-feu", conditions={"env": "prod"}, kinds=["procedure"]), ["prod"])
        self.assertEqual(self.ids("pare-feu", conditions={"env": "prod"}, kinds=["observation"]), [])

    def test_dimension_mismatch_is_refused(self):
        self.memory.remember(FIREWALL, source_id="fw")
        bigger = HashEmbedder(dim=2048)
        bigger.model_id = HashEmbedder.model_id
        projection = QdrantProjection(self.memory, embed=bigger, transport=self.qdrant)
        with self.assertRaises(MemoryError):
            projection.query("firewall", 5)

    def test_prefixes_are_applied_and_change_the_model_tag(self):
        seen = []

        class Recording(HashEmbedder):
            def __call__(self, texts):
                seen.extend(texts)
                return super().__call__(texts)

        projection = QdrantProjection(self.memory, embed=Recording(), transport=FakeQdrant(),
                                      query_prefix="q: ", document_prefix="d: ")
        self.memory.attach_projection(projection)
        self.memory.remember(FIREWALL, source_id="fw")
        projection.query("firewall", 5)
        self.assertIn("d: " + FIREWALL, seen)
        self.assertIn("q: firewall", seen)
        self.assertNotEqual(projection.model_tag, self.projection.model_tag)

    def test_configuration_errors(self):
        with self.assertRaises(MemoryError):
            QdrantProjection(self.memory, "http://127.0.0.1:6333", None)
        with self.assertRaises(MemoryError):
            QdrantREST("file:///etc/passwd")
        with self.assertRaises(MemoryError):
            QdrantProjection(self.memory, embed=self.embed, transport=self.qdrant, collection="bad/name")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, status, value):
        raw = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.seen.append((self.path, self.headers.get("Authorization"), self.headers.get("api-key"), body))
        if self.path == "/v1/embeddings":
            data = [{"index": i, "embedding": [float(len(t)), 1.0]} for i, t in enumerate(body["input"])]
            return self._json(200, {"data": list(reversed(data))})
        self._json(500, {"status": {"error": "boom"}})

    def do_GET(self):
        self.server.seen.append((self.path, None, self.headers.get("api-key"), None))
        self._json(404, {"status": {"error": "Not found"}})


class HttpClients(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.seen = []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_openai_embeddings_keeps_input_order_and_sends_the_key(self):
        embed = OpenAIEmbeddings(self.url + "/v1", "m", api_key="k", batch=2)
        self.assertEqual(embed(["a", "bbb", "cc"]), [[1.0, 1.0], [3.0, 1.0], [2.0, 1.0]])
        self.assertEqual([s[1] for s in self.server.seen], ["Bearer k", "Bearer k"])
        self.assertEqual(embed.model_id, "openai:m")

    def test_qdrant_rest_maps_errors(self):
        rest = QdrantREST(self.url, api_key="secret")
        self.assertIsNone(rest("GET", "/collections/x", allow_404=True))
        with self.assertRaises(QdrantError):
            rest("GET", "/collections/x")
        with self.assertRaises(QdrantError):
            rest("POST", "/collections/x/points/query", {"query": [1.0]})
        self.assertEqual({s[2] for s in self.server.seen}, {"secret"})


if __name__ == "__main__":
    unittest.main()
