"""The public import name `persistent_memory` exposes the same objects as `hermes_memory`."""
import tempfile
import unittest

import hermes_memory
import hermes_memory.core
import hermes_memory.persistent
import hermes_memory.qdrant_projection
import persistent_memory


class PublicName(unittest.TestCase):
    def test_same_objects(self):
        self.assertIs(persistent_memory.PersistentMemory, hermes_memory.persistent.PersistentMemory)
        self.assertIs(persistent_memory.MemoryError, hermes_memory.core.MemoryError)
        self.assertIs(persistent_memory.Ref, hermes_memory.core.Ref)
        self.assertIs(persistent_memory.OPERATIONS, hermes_memory.persistent.OPERATIONS)
        self.assertIs(persistent_memory.QdrantProjection, hermes_memory.qdrant_projection.QdrantProjection)
        self.assertIs(persistent_memory.OpenAIEmbeddings, hermes_memory.qdrant_projection.OpenAIEmbeddings)
        self.assertEqual(persistent_memory.__version__, hermes_memory.__version__)
        for name in persistent_memory.__all__:
            self.assertTrue(hasattr(persistent_memory, name), name)

    def test_round_trip_through_public_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = persistent_memory.PersistentMemory(tmp + "/store", "w", create=True)
            port = memory.remember("The relay listens on port 7100.", source_id="relay")
            self.assertEqual([i["artifact_id"] for i in memory.search("relay 7100")["items"]], ["relay"])
            memory.withdraw("relay", "decommissioned")
            self.assertFalse(memory.read(port["ref"])["allowed"])
            self.assertEqual(memory.search("relay 7100")["items"], [])


if __name__ == "__main__":
    unittest.main()
