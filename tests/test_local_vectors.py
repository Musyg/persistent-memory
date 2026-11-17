"""Local vector projection (--semantic): search by meaning, never past the authority."""
import argparse
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from hermes_memory import local_vectors
from hermes_memory.core import MemoryError
from hermes_memory.local_vectors import FastEmbedEmbeddings, LocalVectorProjection
from hermes_memory.mcp_server import add_projection_options, attach_projection
from hermes_memory.persistent import PersistentMemory

# A toy model: words of one concept share a dimension, so "pet" finds "cat" without a common word.
CONCEPTS = [{"cat", "pet", "kitten", "chat"}, {"port", "listens", "socket"}, {"backup", "sauvegarde", "nightly"},
            {"deploy", "release", "tuesday"}]


def toy_vector(text):
    words = {w.strip(".,?!'").lower() for w in text.split()}
    vector = [float(len(words & concept)) for concept in CONCEPTS] + [0.05]
    return vector


class ToyEmbeddings:
    model_id = "toy:concepts-v1"

    def __init__(self):
        self.calls = 0

    def __call__(self, texts):
        self.calls += len(texts)
        return [toy_vector(t) for t in texts]


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Path(self._tmp.name) / "store"
        self.memory = PersistentMemory(self.store, "ws", create=True)
        self.embed = ToyEmbeddings()

    def tearDown(self):
        self._tmp.cleanup()

    def attach(self, memory=None, **kwargs):
        memory = memory or self.memory
        projection = LocalVectorProjection(memory, self.embed, min_score=kwargs.pop("min_score", 0.5), **kwargs)
        self.assertEqual(memory.attach_projection(projection), "ok")
        return projection

    def texts(self, query, memory=None):
        return [i["text"] for i in (memory or self.memory).search(query)["items"]]


class Searching(Base):
    def test_meaning_without_a_shared_word(self):
        self.memory.remember("The cat is called Mika.")
        self.memory.remember("Deploys happen on Tuesday.")
        self.assertEqual(self.texts("pet name"), [])  # keyword search alone finds nothing
        self.attach()
        result = self.memory.search("pet name")
        self.assertEqual([i["text"] for i in result["items"]], ["The cat is called Mika."])
        self.assertEqual(result["semantic"], {"projection": "local", "status": "ok", "candidates": 1})
        self.assertTrue((self.store / "vectors.db").is_file())

    def test_below_min_score_is_not_proposed(self):
        self.memory.remember("The cat is called Mika.")
        projection = self.attach(min_score=0.99)
        self.assertEqual(projection.query("a kitten and a socket", 5), [])
        self.assertEqual(len(projection.query("kitten", 5)), 1)

    def test_vectors_hold_refs_not_text(self):
        self.memory.remember("The cat is called Mika.")
        self.attach()
        with closing(sqlite3.connect(self.store / "vectors.db")) as c, c:
            columns = [r[1] for r in c.execute("PRAGMA table_info(vectors)")]
            dump = "\n".join(c.iterdump())
        self.assertNotIn("text", columns)
        self.assertNotIn("Mika", dump)

    def test_workspaces_do_not_mix(self):
        self.memory.remember("The cat is called Mika.")
        self.attach()
        other = PersistentMemory(self.store, "other")
        projection = self.attach(other)
        self.assertEqual(projection.query("pet", 5), [])
        self.assertEqual(self.texts("pet", other), [])

    def test_pure_python_scoring_matches(self):
        for text in ("The cat is called Mika.", "Backup runs nightly.", "The port listens on 6543."):
            self.memory.remember(text)
        projection = self.attach(min_score=0.1)
        expected = projection.query("pet and nightly backup", 5)
        with mock.patch.object(local_vectors, "_np", None):
            self.assertEqual(projection.query("pet and nightly backup", 5), expected)
        self.assertEqual(len(expected), 2)


class Revalidation(Base):
    def test_correction_and_withdrawal_are_followed(self):
        port = self.memory.remember("The staging port listens on 6543.", source_id="db-port")
        rule = self.memory.derive("Open socket 6543 on the firewall.", parents=[port["ref"]])
        projection = self.attach()
        self.assertEqual(len(projection.query("socket", 5)), 2)
        self.memory.correct("db-port", "The staging port listens on 6544.",
                            expected_version=port["ref"]["version_id"])
        self.assertEqual(self.texts("socket"), ["The staging port listens on 6544."])
        self.assertNotIn(rule["ref"], projection.query("socket", 5))
        self.memory.withdraw("db-port", "decommissioned")
        self.assertEqual(self.texts("socket"), [])
        self.assertEqual(projection.query("socket", 5), [])

    def test_a_stale_vector_cannot_bring_a_version_back(self):
        port = self.memory.remember("The staging port listens on 6543.", source_id="db-port")
        projection = self.attach()
        with closing(sqlite3.connect(projection.path)) as c, c:
            saved = c.execute("SELECT * FROM vectors").fetchall()
        self.memory.withdraw("db-port", "decommissioned")
        with closing(sqlite3.connect(projection.path)) as c, c:  # as if the purge had not happened
            c.executemany("INSERT OR REPLACE INTO vectors VALUES (?,?,?,?,?,?,?)", saved)
        self.assertEqual(projection.query("socket", 5), [port["ref"]])
        result = self.memory.search("socket")
        self.assertEqual(result["items"], [])
        self.assertIn(port["ref"], [e["ref"] for e in result["exclusions"]])

    def test_a_forged_row_is_ignored(self):
        self.memory.remember("The cat is called Mika.")
        projection = self.attach()
        with closing(sqlite3.connect(projection.path)) as c, c:
            row = list(c.execute("SELECT * FROM vectors").fetchone())
            row[0], row[3] = "forged-point", "m-forged"
            c.execute("INSERT INTO vectors VALUES (?,?,?,?,?,?,?)", row)
        self.assertEqual(len(projection.query("pet", 5)), 1)
        self.assertNotIn("m-forged", [r["artifact_id"] for r in projection.query("pet", 5)])

    def test_only_new_versions_are_embedded(self):
        self.memory.remember("The cat is called Mika.")
        self.attach()
        before = self.embed.calls
        self.memory.remember("Backup runs nightly.")
        self.assertEqual(self.embed.calls, before + 1)


class FastEmbedAdapter(unittest.TestCase):
    def test_missing_extra_is_a_setup_error(self):
        with mock.patch("importlib.util.find_spec", return_value=None):
            with self.assertRaisesRegex(MemoryError, "semantic_needs_fastembed"):
                FastEmbedEmbeddings()

    def test_entries_and_queries_use_their_own_embedding(self):
        seen = {}

        class TextEmbedding:
            def __init__(self, model_name, threads=None, cache_dir=None):
                seen["init"] = (model_name, cache_dir)

            def passage_embed(self, texts):
                return ([1.0, 0.0] for _ in texts)

            def query_embed(self, texts):
                return ([0.0, 1.0] for _ in texts)

        stub = types.ModuleType("fastembed")
        stub.TextEmbedding = TextEmbedding
        with mock.patch.dict(sys.modules, {"fastembed": stub}), \
                mock.patch("importlib.util.find_spec", return_value=object()):
            embed = FastEmbedEmbeddings("some/model", cache_dir=Path("models"))
            self.assertNotIn("init", seen)  # loaded on first use only
            self.assertEqual(embed(["a", "b"]), [[1.0, 0.0], [1.0, 0.0]])
            self.assertEqual(embed.query(["q"]), [[0.0, 1.0]])
        self.assertEqual(seen["init"], ("some/model", "models"))
        self.assertEqual(embed.model_id, "fastembed:some/model")

    def test_the_model_is_ready_before_the_first_tool_call(self):
        loads = []

        class TextEmbedding:
            def __init__(self, **kwargs):
                loads.append(kwargs["model_name"])

        stub = types.ModuleType("fastembed")
        stub.TextEmbedding = TextEmbedding
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {"fastembed": stub}), \
                mock.patch("importlib.util.find_spec", return_value=object()):
            memory = PersistentMemory(Path(tmp) / "s", "ws", create=True)  # empty: nothing to embed
            self.assertEqual(memory.attach_projection(LocalVectorProjection(memory, FastEmbedEmbeddings("m"))), "ok")
        self.assertEqual(loads, ["m"])

    def test_a_model_that_cannot_load_leaves_keyword_search(self):
        class TextEmbedding:
            def __init__(self, **kwargs):
                raise RuntimeError("no network")

        stub = types.ModuleType("fastembed")
        stub.TextEmbedding = TextEmbedding
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {"fastembed": stub}), \
                mock.patch("importlib.util.find_spec", return_value=object()):
            memory = PersistentMemory(Path(tmp) / "s", "ws", create=True)
            memory.remember("The cat is called Mika.")
            projection = LocalVectorProjection(memory, FastEmbedEmbeddings("m"))
            self.assertEqual(memory.attach_projection(projection), "unavailable")
            self.assertEqual(memory.search("cat")["semantic"]["status"], "unavailable")
            self.assertEqual([i["text"] for i in memory.search("cat")["items"]], ["The cat is called Mika."])


class Options(Base):
    def options(self, *argv):
        parser = argparse.ArgumentParser()
        add_projection_options(parser)
        return parser.parse_args(list(argv))

    def test_semantic_and_qdrant_are_exclusive(self):
        with self.assertRaisesRegex(MemoryError, "choose_semantic_or_qdrant"):
            attach_projection(self.memory, self.options("--semantic", "--qdrant-url", "http://127.0.0.1:6333"))

    def test_embed_url_needs_a_model(self):
        with self.assertRaisesRegex(MemoryError, "embed_url_needs_embed_model"):
            attach_projection(self.memory, self.options("--semantic", "--embed-url", "http://127.0.0.1:1/v1"))

    def test_default_threshold_follows_the_model(self):
        made = []
        with mock.patch.object(local_vectors, "FastEmbedEmbeddings", lambda *a, **k: ToyEmbeddings()), \
                mock.patch.object(local_vectors.LocalVectorProjection, "__init__",
                                  lambda self, memory, embed, **k: made.append(k) or None), \
                mock.patch.object(PersistentMemory, "attach_projection", lambda self, p: "ok"):
            attach_projection(self.memory, self.options("--semantic"))
            attach_projection(self.memory, self.options("--semantic", "--embed-model", "other/model"))
            attach_projection(self.memory, self.options("--semantic", "--semantic-min-score", "0.7"))
        self.assertEqual([k["min_score"] for k in made], [local_vectors.DEFAULT_MIN_SCORE, 0.5, 0.7])

    def test_without_semantic_nothing_is_attached(self):
        self.assertIsNone(attach_projection(self.memory, self.options()))
        self.assertFalse((self.store / "vectors.db").exists())


if __name__ == "__main__":
    unittest.main()
