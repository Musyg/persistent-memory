"""The Qdrant projection against a real Qdrant server, and optionally a real embedding model.

    PERSISTENT_MEMORY_TEST_QDRANT_URL=http://127.0.0.1:6333 \
    PERSISTENT_MEMORY_TEST_EMBED_URL=http://127.0.0.1:8000/v1 PERSISTENT_MEMORY_TEST_EMBED_MODEL=name \
    python -m unittest discover -s tests_integration

Without a server URL every test is reported as SKIPPED with its reason, never as passed. It
lives outside tests/ because the installed-distribution check counts a skip as a failure.
Use a disposable Qdrant: the tests create and delete their own collections.
"""
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from hermes_memory.persistent import PersistentMemory  # noqa: E402
from hermes_memory.qdrant_projection import OpenAIEmbeddings, QdrantProjection, QdrantREST  # noqa: E402
from qdrant_fake import HashEmbedder  # noqa: E402

QDRANT = os.environ.get("PERSISTENT_MEMORY_TEST_QDRANT_URL")
EMBED_URL = os.environ.get("PERSISTENT_MEMORY_TEST_EMBED_URL")
EMBED_MODEL = os.environ.get("PERSISTENT_MEMORY_TEST_EMBED_MODEL")
MIN_SCORE = float(os.environ.get("PERSISTENT_MEMORY_TEST_MIN_SCORE", "0.5"))
QUERY_PREFIX = os.environ.get("PERSISTENT_MEMORY_TEST_QUERY_PREFIX", "")
DOCUMENT_PREFIX = os.environ.get("PERSISTENT_MEMORY_TEST_DOCUMENT_PREFIX", "")


class Base(unittest.TestCase):
    prefixes = ("", "")

    def embedder(self):
        return HashEmbedder(), 0.5

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.memory = PersistentMemory(Path(self._tmp.name) / "store", "ws", create=True)
        embed, min_score = self.embedder()
        self.rest = QdrantREST(QDRANT)
        self.collection = "pm-test-" + uuid.uuid4().hex[:12]
        self.projection = QdrantProjection(self.memory, QDRANT, embed, collection=self.collection,
                                           min_score=min_score, query_prefix=self.prefixes[0],
                                           document_prefix=self.prefixes[1])
        self.assertEqual(self.memory.attach_projection(self.projection), "ok")

    def tearDown(self):
        self.rest("DELETE", "/collections/" + self.collection, allow_404=True)
        self._tmp.cleanup()

    def count(self):
        info = self.rest("POST", "/collections/%s/points/count" % self.collection, {"exact": True}) \
            if self.rest("GET", "/collections/" + self.collection, allow_404=True) else {"count": 0}
        return info["count"]

    def ids(self, query, **kwargs):
        return [i["artifact_id"] for i in self.memory.search(query, **kwargs)["items"]]


@unittest.skipUnless(QDRANT, "set PERSISTENT_MEMORY_TEST_QDRANT_URL to a disposable Qdrant server")
class RealQdrant(Base):
    def test_lifecycle_on_a_real_server(self):
        src = self.memory.remember("Pour Orion-Test, ouvrir le port 9300 sur le pare-feu.", source_id="fw")
        self.memory.remember("La couleur de la marque est le vert sapin.", source_id="color")
        self.assertEqual(self.count(), 2)
        self.assertEqual(self.ids("firewall"), ["fw"])
        self.memory.correct("fw", "Pour Orion-Test, ouvrir le port 9400 sur le pare-feu.",
                            expected_version=src["ref"]["version_id"])
        self.assertEqual(self.count(), 2)
        self.memory.withdraw("fw", "obsolete")
        self.assertEqual(self.count(), 1)
        self.assertEqual(self.ids("firewall"), [])
        self.assertEqual(self.projection.sync()["added"], 0)

    def test_stale_point_is_refused_by_revalidation(self):
        self.memory.remember("Pour Orion-Test, ouvrir le port 9300 sur le pare-feu.", source_id="fw")
        good = self.projection.transport
        self.projection.transport = QdrantREST("http://127.0.0.1:9")  # nothing listens there
        self.memory.withdraw("fw", "obsolete")
        self.assertEqual(self.projection.status, "unavailable")
        self.projection.transport = good
        self.assertEqual(self.count(), 1)
        result = self.memory.search("firewall")
        self.assertEqual(result["items"], [])
        self.assertIn("source_revoked", {e["reason"] for e in result["exclusions"]})


@unittest.skipUnless(QDRANT and EMBED_URL and EMBED_MODEL,
                     "set PERSISTENT_MEMORY_TEST_QDRANT_URL, _EMBED_URL and _EMBED_MODEL for a real model")
class RealModel(Base):
    prefixes = (QUERY_PREFIX, DOCUMENT_PREFIX)

    def embedder(self):
        return OpenAIEmbeddings(EMBED_URL, EMBED_MODEL), MIN_SCORE

    def test_paraphrase_is_found_and_withdrawal_holds(self):
        self.memory.remember("The staging server Orion-Test listens on TCP port 9300.", source_id="port")
        self.memory.remember("Our brand colour is fir green.", source_id="color")
        self.memory.remember("Invoices are sent on the last working day of the month.", source_id="invoices")
        question = "which socket number accepts connections from clients at preproduction"
        lexical = PersistentMemory(self.memory.root, "ws")
        self.assertEqual(lexical.search(question)["items"], [])
        found = self.ids(question)
        self.assertEqual(found[:1], ["port"])
        self.assertNotIn("invoices", found)
        self.memory.withdraw("port", "obsolete")
        self.assertNotIn("port", self.ids(question))


if __name__ == "__main__":
    unittest.main()
