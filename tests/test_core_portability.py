"""Portability guards for the pinned core: connections are closed, anchor writes survive Windows.

Every test runs on Linux, macOS and Windows; Windows behaviour is simulated through core.WINDOWS.
"""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from hermes_memory import core
from hermes_memory import typed_memory
from hermes_memory.typed_memory import TypedMemory


def is_closed(connection):
    try:
        connection.cursor()
    except sqlite3.ProgrammingError:
        return True
    return False


def failing_pragma_connect(made, prefix):
    """sqlite3.connect replacement whose connection refuses one PRAGMA."""
    real = sqlite3.connect

    def connect(*args, **kwargs):
        base = kwargs.get("factory", sqlite3.Connection)

        class Failing(base):
            def execute(self, sql, *rest):
                if sql.startswith(prefix):
                    raise sqlite3.OperationalError("injected pragma failure")
                return super().execute(sql, *rest)

        kwargs["factory"] = Failing
        connection = real(*args, **kwargs)
        made.append(connection)
        return connection
    return connect


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def leftovers(self, directory):
        return sorted(p.name for p in directory.iterdir() if p.name.endswith(".tmp"))


class ConnectionLifetime(Base):
    def test_every_core_operation_closes_its_connections(self):
        opened = []
        real = core.connect

        def recording(*args, **kwargs):
            connection = real(*args, **kwargs)
            opened.append(connection)
            return connection

        root = self.root
        with patch.object(core, "connect", recording):
            authority = core.Authority.create(root / "authority.db", root / "anchor.json")
            authority = core.Authority.open(root / "authority.db", root / "anchor.json")
            memory = core.Memory.create(root / "content.db", authority)
            memory = core.Memory.open(root / "content.db", authority)
            a = memory.register_source("w", "A", "alpha copper", "a.md")["ref"]
            b = memory.register_source("w", "B", "beta copper")["ref"]
            f = memory.derive("w", "F", "alpha beta", "fact", [{"ref": a, "relation": "derives"}], memory.checkpoint()["epoch"])["ref"]
            self.assertTrue(memory.read(a)["allowed"])
            memory.validate([a, b])
            memory.search("w", "copper")
            memory.resolve("w", "a.md")
            memory.rename(b, "b.md")
            memory.aliases("w")
            memory.plan_revocation("w", "A")
            memory.project(f)
            memory.projection_search("w", "alpha")
            memory.reconcile(apply=True)
            memory.drain_outbox()
            memory.backup(root / "old.db")
            memory.revoke_source("w", "A", "r1")
            memory.get_revocation("r1")
            memory.set_status(b, "archived")
            memory.explain_artifact(f)
            old = core.Memory.open(root / "old.db", authority)
            with self.assertRaises(core.MemoryError):
                old.restore_verify({"stale": True})  # raises inside the with-block
            old.restore_verify(authority.checkpoint())
            authority.recover_anchor(authority.checkpoint())
        self.assertGreater(len(opened), 40)
        still_open = [i for i, connection in enumerate(opened) if not is_closed(connection)]
        self.assertEqual(still_open, [])
        # Windows refuses to delete a file that an open connection holds.
        for name in ("authority.db", "content.db", "old.db", "anchor.json"):
            os.unlink(root / name)

    def test_connect_closes_when_a_pragma_fails(self):
        path = self.root / "plain.db"
        with closing(sqlite3.connect(path)) as setup:
            setup.execute("CREATE TABLE t(x)")
        for prefix in ("PRAGMA foreign_keys", "PRAGMA synchronous"):
            with self.subTest(prefix=prefix):
                made = []
                with patch.object(core.sqlite3, "connect", failing_pragma_connect(made, prefix)):
                    with self.assertRaisesRegex(sqlite3.OperationalError, "injected pragma failure"):
                        core.connect(path)
                self.assertEqual(len(made), 1)
                self.assertTrue(is_closed(made[0]))
        os.unlink(path)

    def test_typed_index_connect_closes_when_a_pragma_fails(self):
        authority = core.Authority.create(self.root / "authority.db", self.root / "anchor.json")
        memory = core.Memory.create(self.root / "content.db", authority)
        typed = TypedMemory(memory, self.root / "index.db")
        made = []
        with patch.object(typed_memory.sqlite3, "connect", failing_pragma_connect(made, "PRAGMA synchronous")):
            with self.assertRaisesRegex(sqlite3.OperationalError, "injected pragma failure"):
                typed._connect()
        self.assertEqual(len(made), 1)
        self.assertTrue(is_closed(made[0]))
        os.unlink(self.root / "index.db")


class AnchorWrites(Base):
    def windows_open(self, opened):
        """os.open as on Windows: a directory cannot be opened."""
        real = os.open

        def fake(path, flags, *rest, **kwargs):
            opened.append(Path(path))
            if os.path.isdir(path):
                raise PermissionError(13, "Permission denied", str(path))
            return real(path, flags, *rest, **kwargs)
        return fake

    def test_windows_does_not_open_the_directory(self):
        target = self.root / "anchor.json"
        opened = []
        with patch.object(core, "WINDOWS", True), patch.object(core.os, "open", self.windows_open(opened)):
            core.atomic_json(target, {"epoch": 1})
            authority = core.Authority.create(self.root / "authority.db", self.root / "store" / "anchor.json")
            memory = core.Memory.create(self.root / "content.db", authority)
            ref = memory.register_source("w", "A", "alpha")["ref"]
            memory.revoke_source("w", "A", "r1")
        self.assertNotIn(self.root, opened)
        self.assertNotIn(self.root / "store", opened)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"epoch": 1})
        self.assertEqual(memory.read(ref)["reason"], "source_revoked")
        self.assertEqual(self.leftovers(self.root), [])

    def test_posix_still_syncs_the_directory(self):
        target = self.root / "anchor.json"
        opened = []
        with patch.object(core, "WINDOWS", False), patch.object(core.os, "open", self.windows_open(opened)):
            with self.assertRaises(PermissionError):
                core.atomic_json(target, {"epoch": 1})
        self.assertIn(self.root, opened)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"epoch": 1})

    def flaky_replace(self, calls, failures):
        real = os.replace

        def fake(src, dst):
            calls.append((src, dst))
            if len(calls) <= failures:
                raise PermissionError(13, "Access is denied", str(dst))
            return real(src, dst)
        return fake

    def test_transient_permission_error_is_retried(self):
        target = self.root / "anchor.json"
        target.write_text("old\n", encoding="utf-8")
        calls, sleeps = [], []
        with patch.object(core, "WINDOWS", True), patch.object(core.os, "replace", self.flaky_replace(calls, 3)), patch.object(core.time, "sleep", sleeps.append):
            core.atomic_json(target, {"epoch": 2})
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(sleeps), 3)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"epoch": 2})
        self.assertEqual(self.leftovers(self.root), [])

    def test_persistent_permission_error_raises_after_bounded_attempts(self):
        target = self.root / "anchor.json"
        target.write_text("old\n", encoding="utf-8")
        for windows, attempts in ((True, 50), (False, 1)):
            with self.subTest(windows=windows):
                calls, sleeps = [], []
                with patch.object(core, "WINDOWS", windows), patch.object(core.os, "replace", self.flaky_replace(calls, 10**6)), patch.object(core.time, "sleep", sleeps.append):
                    with self.assertRaises(PermissionError):
                        core.atomic_json(target, {"epoch": 3})
                self.assertEqual(len(calls), attempts)
                self.assertEqual(len(sleeps), attempts - 1)
                self.assertLessEqual(sum(sleeps), 1.0)
                if windows:
                    self.assertGreaterEqual(sum(sleeps), 0.5)
                self.assertEqual(target.read_text(encoding="utf-8"), "old\n")
                self.assertEqual(self.leftovers(self.root), [])

    def test_retry_keeps_the_store_usable_after_commit(self):
        authority = core.Authority.create(self.root / "authority.db", self.root / "anchor.json")
        memory = core.Memory.create(self.root / "content.db", authority)
        ref = memory.register_source("w", "A", "alpha")["ref"]
        calls = []
        with patch.object(core, "WINDOWS", True), patch.object(core.os, "replace", self.flaky_replace(calls, 2)), patch.object(core.time, "sleep", lambda seconds: None):
            memory.revoke_source("w", "A", "r1")
        self.assertEqual(len(calls), 3)
        self.assertEqual(memory.read(ref)["reason"], "source_revoked")
        self.assertEqual(authority.checkpoint()["epoch"], 2)
        self.assertEqual(self.leftovers(self.root), [])


if __name__ == "__main__":
    unittest.main()
