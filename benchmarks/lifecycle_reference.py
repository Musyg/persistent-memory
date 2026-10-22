"""Independent SQLite lifecycle reference used only by run_benchmark.py.

Both profiles enforce the same versions, CAS, scopes and strong dependencies.
The snapshot-local profile additionally rolls back its authority on restore;
it has no external freshness witness. This module is not a second runner.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid
from contextlib import contextmanager


class Rejected(ValueError):
    """Expected lifecycle rejection, distinct from an implementation failure."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def _hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class SQLiteReference:
    def __init__(self, root, *, snapshot_local=False):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.snapshot_local = snapshot_local
        self.authority = self.root / 'authority.db'
        self.content = self.root / 'content.db'
        self.serial = 0
        with self._connect(self.authority) as c:
            c.executescript('''
CREATE TABLE metadata(generation TEXT NOT NULL, epoch INTEGER NOT NULL);
CREATE TABLE objects(workspace TEXT, artifact_id TEXT, version_id TEXT, kind TEXT,
 digest TEXT, dependencies TEXT, PRIMARY KEY(workspace,artifact_id,version_id));
CREATE TABLE heads(workspace TEXT, artifact_id TEXT, version_id TEXT,
 PRIMARY KEY(workspace,artifact_id));
CREATE TABLE revoked(workspace TEXT, artifact_id TEXT, PRIMARY KEY(workspace,artifact_id));
CREATE TABLE requests(event_id TEXT PRIMARY KEY, payload TEXT, epoch INTEGER);
CREATE TABLE journal(epoch INTEGER PRIMARY KEY, payload TEXT NOT NULL);
''')
            c.execute('INSERT INTO metadata VALUES (?,0)', (uuid.uuid4().hex,))
        with self._connect(self.content) as c:
            c.executescript('''
CREATE TABLE content(ref TEXT PRIMARY KEY, text TEXT NOT NULL);
CREATE TABLE metadata(ready INTEGER NOT NULL);
INSERT INTO metadata VALUES (1);
''')

    @staticmethod
    @contextmanager
    def _connect(path):
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA synchronous=FULL')
        try:
            with c:
                yield c
        finally:
            c.close()

    @staticmethod
    def _identity(ref):
        return (ref['workspace'], ref['artifact_id'], ref['version_id'])

    def checkpoint(self):
        with self._connect(self.authority) as c:
            row = c.execute('SELECT generation,epoch FROM metadata').fetchone()
            return dict(row)

    def _valid(self, c, ref, seen=None):
        seen = set() if seen is None else set(seen)
        identity = self._identity(ref)
        if identity in seen or len(seen) > 64:
            return False, 'dependency_invalid'
        seen.add(identity)
        row = c.execute('SELECT * FROM objects WHERE workspace=? AND artifact_id=? AND version_id=?', identity).fetchone()
        if row is None:
            return False, 'unknown_ref'
        if c.execute('SELECT 1 FROM revoked WHERE workspace=? AND artifact_id=?', identity[:2]).fetchone():
            return False, 'source_revoked'
        head = c.execute('SELECT version_id FROM heads WHERE workspace=? AND artifact_id=?', identity[:2]).fetchone()
        if head is None or head[0] != ref['version_id']:
            return False, 'version_not_current'
        for dependency in json.loads(row['dependencies']):
            if dependency['relation'] in {'derives', 'indexes'}:
                valid, reason = self._valid(c, dependency['ref'], seen)
                if not valid:
                    return False, reason
        return True, 'allowed'

    def _event(self, c, payload):
        epoch = c.execute('SELECT epoch FROM metadata').fetchone()[0] + 1
        c.execute('INSERT INTO journal VALUES (?,?)', (epoch, _canonical(payload)))
        c.execute('UPDATE metadata SET epoch=?', (epoch,))
        return epoch

    def _put(self, workspace, artifact_id, text, kind, dependencies, expected_version, checkpoint):
        for dependency in dependencies:
            if dependency['relation'] not in {'derives', 'indexes', 'cites', 'navigates'}:
                raise Rejected('invalid_dependency')
            if dependency['ref']['workspace'] != workspace:
                raise Rejected('scope_mismatch')
            if dependency['ref']['artifact_id'] == artifact_id:
                raise Rejected('self_dependency')
        dependencies = sorted(dependencies, key=_canonical)
        if len({_canonical(d) for d in dependencies}) != len(dependencies):
            raise Rejected('duplicate_dependency')
        if kind != 'source' and not any(d['relation'] in {'derives', 'indexes'} for d in dependencies):
            raise Rejected('derivation_required')
        with self._connect(self.authority) as c:
            c.execute('BEGIN IMMEDIATE')
            if checkpoint is not None:
                current_epoch = c.execute('SELECT epoch FROM metadata').fetchone()[0]
                if checkpoint['epoch'] != current_epoch:
                    raise Rejected('stale_epoch')
            if c.execute('SELECT 1 FROM revoked WHERE workspace=? AND artifact_id=?', (workspace, artifact_id)).fetchone():
                raise Rejected('source_revoked')
            head = c.execute('SELECT version_id FROM heads WHERE workspace=? AND artifact_id=?', (workspace, artifact_id)).fetchone()
            if head:
                previous = c.execute('SELECT * FROM objects WHERE workspace=? AND artifact_id=? AND version_id=?', (workspace, artifact_id, head[0])).fetchone()
                if previous['kind'] != kind:
                    raise Rejected('kind_conflict')
                if previous['digest'] == _hash(text) and previous['dependencies'] == _canonical(dependencies):
                    for dependency in dependencies:
                        if dependency['relation'] in {'derives', 'indexes'}:
                            valid, reason = self._valid(c, dependency['ref'])
                            if not valid:
                                raise Rejected(reason)
                    return {'ref': {'workspace': workspace, 'artifact_id': artifact_id, 'version_id': head[0]}, 'idempotent': True}
            if (head[0] if head else None) != expected_version:
                raise Rejected('version_conflict')
            for dependency in dependencies:
                if dependency['relation'] in {'derives', 'indexes'}:
                    valid, reason = self._valid(c, dependency['ref'])
                    if not valid:
                        raise Rejected(reason)
            ref = {'workspace': workspace, 'artifact_id': artifact_id, 'version_id': uuid.uuid4().hex}
            with self._connect(self.content) as data:
                if data.execute('SELECT ready FROM metadata').fetchone()[0] != 1:
                    raise Rejected('restore_quarantine')
                data.execute('INSERT INTO content VALUES (?,?)', (_canonical(ref), text))
            epoch = self._event(c, {'op': 'put', 'ref': ref, 'digest': _hash(text), 'dependencies': dependencies})
            c.execute('INSERT INTO objects VALUES (?,?,?,?,?,?)', (*self._identity(ref), kind, _hash(text), _canonical(dependencies)))
            c.execute('INSERT INTO heads VALUES (?,?,?) ON CONFLICT(workspace,artifact_id) DO UPDATE SET version_id=excluded.version_id', self._identity(ref))
            return {'ref': ref, 'epoch': epoch}

    def put_source(self, workspace, artifact_id, text, expected_version=None):
        return self._put(workspace, artifact_id, text, 'source', [], expected_version, None)

    def derive(self, workspace, artifact_id, text, dependencies, checkpoint, expected_version=None):
        return self._put(workspace, artifact_id, text, 'fact', dependencies, expected_version, checkpoint)

    def read(self, ref):
        with self._connect(self.content) as data, self._connect(self.authority) as c:
            if data.execute('SELECT ready FROM metadata').fetchone()[0] != 1:
                return {'allowed': False, 'reason': 'restore_quarantine'}
            valid, reason = self._valid(c, ref)
            if not valid:
                return {'allowed': False, 'reason': reason}
            stored = data.execute('SELECT text FROM content WHERE ref=?', (_canonical(ref),)).fetchone()
            if stored is None:
                return {'allowed': False, 'reason': 'content_missing'}
            row = c.execute('SELECT digest FROM objects WHERE workspace=? AND artifact_id=? AND version_id=?', self._identity(ref)).fetchone()
            if _hash(stored[0]) != row[0]:
                raise Rejected('content_digest_mismatch')
            return {'allowed': True, 'content': stored[0], 'reason': 'allowed'}

    def revoke(self, workspace, artifact_id, event_id):
        payload = _canonical({'workspace': workspace, 'artifact_id': artifact_id})
        with self._connect(self.authority) as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT payload,epoch FROM requests WHERE event_id=?', (event_id,)).fetchone()
            if old:
                if old[0] != payload:
                    raise Rejected('event_id_conflict')
                return {'event_id': event_id, 'epoch': old[1], 'registered': True}
            epoch = self._event(c, {'op': 'revoke', 'workspace': workspace, 'artifact_id': artifact_id, 'event_id': event_id})
            c.execute('INSERT OR IGNORE INTO revoked VALUES (?,?)', (workspace, artifact_id))
            c.execute('INSERT INTO requests VALUES (?,?,?)', (event_id, payload, epoch))
            return {'event_id': event_id, 'epoch': epoch, 'registered': True}

    def _copy(self, source, destination):
        with self._connect(source) as original, self._connect(destination) as target:
            original.backup(target)

    def backup(self):
        self.serial += 1
        folder = self.root / ('backup-' + str(self.serial))
        folder.mkdir()
        self._copy(self.content, folder / 'content.db')
        with self._connect(folder / 'content.db') as c:
            c.execute('UPDATE metadata SET ready=0')
        if self.snapshot_local:
            self._copy(self.authority, folder / 'authority.db')
        return folder

    def restore(self, backup):
        self.serial += 1
        self.content = self.root / ('restored-content-' + str(self.serial) + '.db')
        self._copy(backup / 'content.db', self.content)
        if self.snapshot_local:
            self.authority = self.root / ('restored-authority-' + str(self.serial) + '.db')
            self._copy(backup / 'authority.db', self.authority)

    def verify_restore(self, checkpoint):
        if checkpoint != self.checkpoint():
            raise Rejected('restore_fresh_checkpoint_required')
        with self._connect(self.content) as data:
            if data.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise Rejected('snapshot_integrity_failed')
            data.execute('UPDATE metadata SET ready=1')
        return {'ready': True}

    def reopen(self):
        # Connections are per operation. Reopening validates the active files.
        with self._connect(self.authority) as c, self._connect(self.content) as data:
            c.execute('SELECT generation,epoch FROM metadata').fetchone()
            data.execute('SELECT ready FROM metadata').fetchone()


class HermesAdapter:
    def __init__(self, root):
        from hermes_memory import Authority, Memory
        self.root = Path(root)
        self.authority = Authority.create(self.root / 'authority.db', self.root / 'anchor.json')
        self.memory = Memory.create(self.root / 'content.db', self.authority)
        self.serial = 0

    def checkpoint(self):
        return self.memory.checkpoint()

    def put_source(self, workspace, artifact_id, text, expected_version=None):
        return self.memory.register_source(workspace, artifact_id, text, expected_version=expected_version)

    def derive(self, workspace, artifact_id, text, dependencies, checkpoint, expected_version=None):
        return self.memory.derive(workspace, artifact_id, text, 'fact', dependencies,
                                  checkpoint['epoch'], expected_version=expected_version)

    def read(self, ref):
        return self.memory.read(ref)

    def revoke(self, workspace, artifact_id, event_id):
        return self.memory.revoke_source(workspace, artifact_id, event_id)

    def backup(self):
        self.serial += 1
        path = self.root / ('backup-' + str(self.serial) + '.db')
        self.memory.backup(path)
        return path

    def restore(self, backup):
        from hermes_memory import Memory
        # Work on a copy so replaying a backup never mutates the saved image.
        self.serial += 1
        path = self.root / ('restored-' + str(self.serial) + '.db')
        path.write_bytes(backup.read_bytes())
        self.memory = Memory.open(path, self.authority)

    def verify_restore(self, checkpoint):
        return self.memory.restore_verify(checkpoint)

    def reopen(self):
        from hermes_memory import Authority, Memory
        self.authority = Authority.open(self.authority.path, self.authority.anchor_path)
        self.memory = Memory.open(self.memory.path, self.authority)
