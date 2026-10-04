"""Local memory authority. Trusted filesystem, separate retained anchor required."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, asdict

GENESIS = hashlib.sha256(b'hermes-memory-core-v1').hexdigest()
RELATIONS = {'derives', 'indexes', 'cites', 'navigates'}
DEPENDENCIES = {'derives', 'indexes'}
STATES = {'active', 'archived', 'expired', 'invalidated'}

class MemoryError(ValueError):
    pass

def require(ok, reason):
    if not ok:
        raise MemoryError(reason)

def canonical(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(',', ':'))

def digest(x):
    return hashlib.sha256(x.encode('utf-8')).hexdigest()

def name(x):
    require(type(x) is str and 0 < len(x.encode('utf-8')) <= 512 and all(ord(c) >= 32 for c in x), 'invalid_identifier')
    return x

@dataclass(frozen=True)
class Ref:
    workspace: str
    artifact_id: str
    version_id: str
    def __post_init__(self):
        for x in asdict(self).values():
            name(x)
    def to_dict(self):
        return asdict(self)

def ref(x):
    if isinstance(x, Ref):
        return x.to_dict()
    require(type(x) is dict and set(x) == {'workspace','artifact_id','version_id'}, 'invalid_ref')
    return Ref(**x).to_dict()

def key(x):
    return canonical(ref(x))

def connect(path, ro=False):
    p = Path(path).resolve()
    require(p.is_file(), 'database_missing')
    c = sqlite3.connect(p.as_uri() + ('?mode=ro' if ro else '?mode=rw'), uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA synchronous=FULL')
    return c

def reserve(path):
    p = Path(path).absolute()
    require(not p.is_symlink(), 'symlink_forbidden')
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    return p.resolve()

def atomic_json(path, value):
    p = Path(path)
    tmp = p.with_name(p.name + '.' + uuid.uuid4().hex + '.tmp')
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(canonical(value) + '\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, p)
    fd = os.open(p.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

class Authority:
    """Authority and anchor MUST be retained independently of Memory snapshots.

    A missing/mismatched anchor always blocks. An actor rolling back both files is
    outside this trusted-local contract. No cryptographic authenticity is claimed.
    """
    def __init__(self, path, anchor_path):
        self.path = Path(path).resolve()
        self.anchor_path = Path(anchor_path).resolve()
        require(self.path != self.anchor_path, 'anchor_separation_required')
        require(self.path.is_file() and self.anchor_path.is_file(), 'authority_or_anchor_missing')
        with self.transaction(False):
            pass

    @classmethod
    def create(cls, path, anchor_path):
        require(Path(path).resolve() != Path(anchor_path).resolve(), 'anchor_separation_required')
        require(not Path(anchor_path).exists(), 'anchor_exists')
        p = reserve(path)
        c = connect(p)
        c.executescript("""
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE events (seq INTEGER PRIMARY KEY, payload TEXT NOT NULL, previous TEXT NOT NULL, digest TEXT NOT NULL);
CREATE TABLE objects (workspace TEXT, artifact_id TEXT, version_id TEXT, kind TEXT NOT NULL, content_sha256 TEXT NOT NULL, dependencies TEXT NOT NULL, provenance_known INTEGER NOT NULL, status TEXT NOT NULL, epoch INTEGER NOT NULL, PRIMARY KEY(workspace,artifact_id,version_id));
CREATE TABLE heads (workspace TEXT, artifact_id TEXT, version_id TEXT NOT NULL, alias TEXT, PRIMARY KEY(workspace,artifact_id), UNIQUE(workspace,alias));
CREATE TABLE aliases (workspace TEXT, alias TEXT, artifact_id TEXT NOT NULL, PRIMARY KEY(workspace,alias));
CREATE TABLE revoked (workspace TEXT, artifact_id TEXT, event_id TEXT UNIQUE, seq INTEGER NOT NULL, PRIMARY KEY(workspace,artifact_id));
CREATE TABLE requests (event_id TEXT PRIMARY KEY, payload TEXT NOT NULL, seq INTEGER NOT NULL);
CREATE TABLE outbox (seq INTEGER PRIMARY KEY, payload TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0);
""")
        generation = uuid.uuid4().hex
        c.executemany('INSERT INTO meta VALUES (?,?)', [('schema','2'),('generation',generation)])
        c.commit(); c.close()
        Path(anchor_path).parent.mkdir(parents=True, exist_ok=True)
        atomic_json(anchor_path, {'generation':generation, 'epoch':0,'digest':GENESIS})
        return cls(p, anchor_path)

    @classmethod
    def open(cls, path, anchor_path):
        return cls(path, anchor_path)

    def _checkpoint(self, c, verify_state=True):
        require(c.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0] == '2', 'schema_mismatch')
        generation = c.execute("SELECT value FROM meta WHERE key='generation'").fetchone()[0]
        previous = GENESIS
        seq = 0
        payloads = []
        for row in c.execute('SELECT * FROM events ORDER BY seq'):
            seq += 1
            require(row['seq'] == seq and row['previous'] == previous, 'ledger_invalid')
            expected = digest(canonical({'seq':seq,'payload':json.loads(row['payload']),'previous':previous}))
            require(row['digest'] == expected, 'ledger_invalid')
            previous = expected
            payloads.append((seq,json.loads(row['payload'])))
        if verify_state:self._verify_state(c,payloads)
        return {'generation':generation,'epoch':seq,'digest':previous}

    def _verify_state(self,c,events):
        expected_objects={};heads={};aliases={};revoked={};requests={}
        for seq,p in events:
            op=p.get('op')
            require(op in {'put','rename','status','revoke'},'unknown_ledger_operation')
            if op=='put':
                r=ref(p['ref']);identity=(r['workspace'],r['artifact_id']);k=key(r)
                require(k not in expected_objects and type(p.get('provenance_known')) is bool,'invalid_put_event')
                expected_objects[k]={'kind':p['kind'],'content_sha256':p['content_sha256'],'dependencies':canonical(p['dependencies']),'provenance_known':int(p['provenance_known']),'status':'active','epoch':seq}
                prior=heads.get(identity,{'alias':None})
                alias=p.get('alias') if p.get('alias') is not None else prior['alias']
                heads[identity]={'version_id':r['version_id'],'alias':alias}
                if alias is not None:
                    pair=(r['workspace'],alias)
                    require(pair not in aliases or aliases[pair]==r['artifact_id'],'alias_ledger_conflict')
                    aliases[pair]=r['artifact_id']
            elif op=='rename':
                r=ref(p['ref']);identity=(r['workspace'],r['artifact_id'])
                require(identity in heads and heads[identity]['version_id']==r['version_id'],'invalid_rename_event')
                pair=(r['workspace'],p['alias'])
                require(pair not in aliases or aliases[pair]==r['artifact_id'],'alias_ledger_conflict')
                aliases[pair]=r['artifact_id'];heads[identity]['alias']=p['alias']
            elif op=='status':
                k=key(p['ref']);require(k in expected_objects and p['status'] in STATES,'invalid_status_event')
                expected_objects[k]['status']=p['status']
            else:
                identity=(p['workspace'],p['source_id']);event_id=name(p['event_id'])
                require(event_id not in requests,'duplicate_revocation_event')
                revoked.setdefault(identity,{'event_id':event_id,'seq':seq})
                requests[event_id]={'payload':canonical(p),'seq':seq}
        actual_objects={}
        for row in c.execute('SELECT * FROM objects'):
            r=Ref(row['workspace'],row['artifact_id'],row['version_id'])
            actual_objects[key(r)]={f:row[f] for f in ('kind','content_sha256','dependencies','provenance_known','status','epoch')}
        actual_heads={(row['workspace'],row['artifact_id']):{'version_id':row['version_id'],'alias':row['alias']} for row in c.execute('SELECT * FROM heads')}
        actual_aliases={(row['workspace'],row['alias']):row['artifact_id'] for row in c.execute('SELECT * FROM aliases')}
        actual_revoked={(row['workspace'],row['artifact_id']):{'event_id':row['event_id'],'seq':row['seq']} for row in c.execute('SELECT * FROM revoked')}
        actual_requests={row['event_id']:{'payload':row['payload'],'seq':row['seq']} for row in c.execute('SELECT * FROM requests')}
        require(actual_objects==expected_objects and actual_heads==heads and actual_aliases==aliases and actual_revoked==revoked and actual_requests==requests,'authority_state_mismatch')

    @contextmanager
    def transaction(self, write=False):
        c = connect(self.path)
        try:
            c.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            cp = self._checkpoint(c)
            try:
                anchor = json.loads(self.anchor_path.read_text(encoding='utf-8'))
            except (OSError, ValueError) as e:
                raise MemoryError('anchor_unavailable') from e
            require(cp == anchor, 'anchor_mismatch')
            yield c
            updated = self._checkpoint(c)
            c.commit()
            if write and updated != cp:
                # Commit precedes anchor. A crash here blocks until explicit repair.
                atomic_json(self.anchor_path, updated)
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def checkpoint(self):
        with self.transaction() as c:
            return self._checkpoint(c)

    def recover_anchor(self, trusted_checkpoint):
        """Explicit monotone repair after committed event/anchor crash.

        Caller must supply the exact committed checkpoint from independent audit;
        this cannot establish freshness when both authority and anchor were lost.
        """
        with connect(self.path) as c:
            c.execute('BEGIN IMMEDIATE')
            cp = self._checkpoint(c)
            require(cp == trusted_checkpoint, 'trusted_checkpoint_mismatch')
            old = json.loads(self.anchor_path.read_text(encoding='utf-8'))
            require(old['generation'] == cp['generation'] and old['epoch'] <= cp['epoch'], 'non_monotone_recovery')
            if old['epoch']:
                row = c.execute('SELECT digest FROM events WHERE seq=?',(old['epoch'],)).fetchone()
                require(row and row[0] == old['digest'], 'anchor_not_prefix')
            else:
                require(old['digest'] == GENESIS, 'anchor_not_prefix')
            atomic_json(self.anchor_path, cp)
            return cp

    def event(self, c, payload):
        cp = self._checkpoint(c,verify_state=False); seq = cp['epoch'] + 1
        require(seq <= 1000000, 'event_limit')
        h = digest(canonical({'seq':seq,'payload':payload,'previous':cp['digest']}))
        c.execute('INSERT INTO events VALUES (?,?,?,?)',(seq,canonical(payload),cp['digest'],h))
        c.execute('INSERT INTO outbox (seq,payload) VALUES (?,?)',(seq,canonical(payload)))
        return seq

class Memory:
    def __init__(self, path, authority):
        self.path = Path(path).resolve()
        self.authority = authority
        require(self.path not in {authority.path,authority.anchor_path}, 'snapshot_separation_required')
        with connect(self.path) as c:
            require(c.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0] == '1','schema_mismatch')
            self.generation = c.execute("SELECT value FROM meta WHERE key='generation'").fetchone()[0]
        require(self.generation == authority.checkpoint()['generation'], 'generation_mismatch')

    @classmethod
    def create(cls, path, authority):
        p = reserve(path); cp = authority.checkpoint()
        with connect(p) as c:
            c.executescript("""
CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE content(ref TEXT PRIMARY KEY, content TEXT NOT NULL);
CREATE TABLE projection(namespace TEXT, point_id TEXT, ref TEXT NOT NULL, epoch INTEGER NOT NULL, content TEXT NOT NULL, PRIMARY KEY(namespace,point_id));
""")
            c.executemany('INSERT INTO meta VALUES (?,?)',[('schema','1'),('generation',cp['generation']),('mode','ready')])
        return cls(p,authority)

    @classmethod
    def open(cls,path,authority):
        return cls(path,authority)

    def checkpoint(self):
        return self.authority.checkpoint()

    def _ready(self,c):
        require(c.execute("SELECT value FROM meta WHERE key='mode'").fetchone()[0] == 'ready','restore_quarantine')

    def _object(self,c,r):
        r=ref(r)
        row=c.execute('SELECT * FROM objects WHERE workspace=? AND artifact_id=? AND version_id=?',tuple(r.values())).fetchone()
        if row:
            event=c.execute('SELECT payload FROM events WHERE seq=?',(row['epoch'],)).fetchone()
            require(event is not None,'object_event_missing')
            payload=json.loads(event[0])
            require(payload.get('op')=='put' and payload.get('ref')==r and payload.get('kind')==row['kind'] and payload.get('content_sha256')==row['content_sha256'] and payload.get('dependencies')==json.loads(row['dependencies']),'object_manifest_mismatch')
            require(type(payload.get('provenance_known')) is bool and payload['provenance_known']==bool(row['provenance_known']),'object_manifest_mismatch')
        return row

    def _valid(self,c,r,seen=None):
        r=ref(r); k=key(r); seen=set() if seen is None else set(seen)
        if k in seen or len(seen)>64: return False,'dependency_cycle_or_depth'
        seen.add(k)
        row=self._object(c,r)
        if row is None: return False,'unknown_ref'
        if c.execute('SELECT 1 FROM revoked WHERE workspace=? AND artifact_id=?',(r['workspace'],r['artifact_id'])).fetchone(): return False,'source_revoked'
        head=c.execute('SELECT version_id FROM heads WHERE workspace=? AND artifact_id=?',(r['workspace'],r['artifact_id'])).fetchone()
        if not head or head[0]!=r['version_id']: return False,'version_not_current'
        if row['status']!='active': return False,row['status']
        if not row['provenance_known']: return False,'provenance_unknown'
        for d in json.loads(row['dependencies']):
            if d['relation'] in DEPENDENCIES:
                allowed,reason=self._valid(c,d['ref'],seen)
                if not allowed: return False,reason
        return True,'allowed'

    def _put(self,workspace,artifact_id,content,kind,dependencies,expected_version,expected_epoch,alias,provenance_known,producer=None):
        name(workspace);name(artifact_id);name(kind)
        require(type(content) is str and len(content.encode('utf-8'))<=1024*1024,'invalid_content')
        require(type(provenance_known) is bool,'invalid_provenance')
        require(expected_version is None or type(expected_version) is str,'invalid_expected_version')
        require(type(dependencies) is list and len(dependencies)<=64,'invalid_dependencies')
        ds=[]
        for d in dependencies:
            require(type(d) is dict and set(d)=={'ref','relation'} and d['relation'] in RELATIONS,'invalid_dependency')
            rr=ref(d['ref']);require(rr['workspace']==workspace,'scope_mismatch')
            require(rr['artifact_id']!=artifact_id,'self_dependency')
            ds.append({'ref':rr,'relation':d['relation']})
        ds=sorted(ds,key=canonical)
        if producer is not None:
            require(type(producer) is dict and set(producer)=={'schema_version','compiler_id','compiler_version','config','config_sha256','input_refs'},'invalid_producer')
            require(type(producer['schema_version']) is int and producer['schema_version']==1,'invalid_producer_schema')
            name(producer['compiler_id']);name(producer['compiler_version'])
            require(type(producer['config']) is dict and len(canonical(producer).encode('utf-8'))<=65536,'producer_limit')
            require(producer['config_sha256']==digest(canonical(producer['config'])),'producer_config_digest')
            require(type(producer['input_refs']) is list and {key(r) for r in producer['input_refs']}=={key(d['ref']) for d in ds if d['relation'] in DEPENDENCIES},'producer_inputs_mismatch')
        require(len({canonical(d) for d in ds})==len(ds),'duplicate_dependency')
        if kind!='source' and provenance_known:
            require(any(d['relation'] in DEPENDENCIES for d in ds),'derivation_required')
        if alias is not None:name(alias)
        with self.authority.transaction(True) as c:
            cp=self.authority._checkpoint(c)
            if expected_epoch is not None:
                require(type(expected_epoch) is int and expected_epoch==cp['epoch'],'stale_epoch')
            require(not c.execute('SELECT 1 FROM revoked WHERE workspace=? AND artifact_id=?',(workspace,artifact_id)).fetchone(),'source_revoked')
            head=c.execute('SELECT * FROM heads WHERE workspace=? AND artifact_id=?',(workspace,artifact_id)).fetchone()
            if alias is not None:
                owned=c.execute('SELECT artifact_id FROM aliases WHERE workspace=? AND alias=?',(workspace,alias)).fetchone()
                require(not owned or owned[0]==artifact_id,'alias_conflict')
            if head:
                current=self._object(c,Ref(workspace,artifact_id,head['version_id']))
                require(current['kind']==kind,'kind_conflict')
                prior_event=json.loads(c.execute('SELECT payload FROM events WHERE seq=?',(current['epoch'],)).fetchone()[0])
                same=(prior_event.get('producer')==producer and current['content_sha256']==digest(content) and current['kind']==kind and current['dependencies']==canonical(ds) and current['provenance_known']==int(provenance_known) and current['status']=='active')
                if same and (alias is None or alias==head['alias']):
                    for d in ds:
                        if d['relation'] in DEPENDENCIES:
                            ok,reason=self._valid(c,d['ref']);require(ok,reason)
                    return {'ref':Ref(workspace,artifact_id,head['version_id']).to_dict(),'epoch':current['epoch'],'idempotent':True}
            require((head['version_id'] if head else None)==expected_version,'version_conflict')
            for d in ds:
                if d['relation'] in DEPENDENCIES:
                    ok,reason=self._valid(c,d['ref']);require(ok,reason)
            rr=Ref(workspace,artifact_id,uuid.uuid4().hex).to_dict()
            h=digest(content)
            seq=self.authority.event(c,{'op':'put','ref':rr,'content_sha256':h,'kind':kind,'dependencies':ds,'producer':producer,'provenance_known':provenance_known,'alias':alias})
            # Data commit before authority commit: a crash can leave only an unreadable orphan.
            with connect(self.path) as data:
                self._ready(data)
                data.execute('INSERT INTO content VALUES (?,?)',(key(rr),content))
            c.execute('INSERT INTO objects VALUES (?,?,?,?,?,?,?,?,?)',(workspace,artifact_id,rr['version_id'],kind,h,canonical(ds),int(provenance_known),'active',seq))
            c.execute('INSERT INTO heads VALUES (?,?,?,?) ON CONFLICT(workspace,artifact_id) DO UPDATE SET version_id=excluded.version_id,alias=COALESCE(excluded.alias,heads.alias)',(workspace,artifact_id,rr['version_id'],alias))
            if alias is not None:c.execute('INSERT OR IGNORE INTO aliases VALUES (?,?,?)',(workspace,alias,artifact_id))
            return {'ref':rr,'epoch':seq}

    def register_source(self,workspace,source_id,content,alias=None,expected_version=None):
        return self._put(workspace,source_id,content,'source',[],expected_version,None,alias,True)

    def derive(self,workspace,artifact_id,content,kind,dependencies,expected_epoch,expected_version=None,provenance_known=True,alias=None,producer=None):
        require(kind!='source','invalid_kind')
        return self._put(workspace,artifact_id,content,kind,dependencies,expected_version,expected_epoch,alias,provenance_known,producer)

    def resolve(self,workspace,alias):
        name(workspace);name(alias)
        with self.authority.transaction() as c:
            row=c.execute('SELECT heads.artifact_id,heads.version_id FROM aliases JOIN heads ON heads.workspace=aliases.workspace AND heads.artifact_id=aliases.artifact_id WHERE aliases.workspace=? AND aliases.alias=?',(workspace,alias)).fetchone()
            return {'ref':Ref(workspace,row[0],row[1]).to_dict() if row else None}

    def rename(self,ref,alias):
        rr=globals()['ref'](ref);name(alias)
        with self.authority.transaction(True) as c:
            ok,reason=self._valid(c,rr);require(ok,reason)
            owner=c.execute('SELECT artifact_id FROM aliases WHERE workspace=? AND alias=?',(rr['workspace'],alias)).fetchone()
            require(not owner or owner[0]==rr['artifact_id'],'alias_conflict')
            c.execute('INSERT OR IGNORE INTO aliases VALUES (?,?,?)',(rr['workspace'],alias,rr['artifact_id']))
            c.execute('UPDATE heads SET alias=? WHERE workspace=? AND artifact_id=?',(alias,rr['workspace'],rr['artifact_id']))
            seq=self.authority.event(c,{'op':'rename','ref':rr,'alias':alias})
            return {'ref':rr,'epoch':seq}

    def aliases(self,workspace):
        name(workspace)
        with self.authority.transaction() as c:
            rows=c.execute('SELECT aliases.alias,heads.artifact_id,heads.version_id FROM aliases JOIN heads ON heads.workspace=aliases.workspace AND heads.artifact_id=aliases.artifact_id WHERE aliases.workspace=? LIMIT 100001',(workspace,)).fetchall()
            require(len(rows)<=100000,'alias_limit')
            return {'epoch':self.authority._checkpoint(c)['epoch'],'aliases':{r[0]:Ref(workspace,r[1],r[2]).to_dict() for r in rows},'complete':True}

    def resolve_many(self,workspace,aliases):
        require(type(aliases) is list and len(aliases)<=1000,'invalid_alias_batch')
        known=self.aliases(workspace)
        return {'epoch':known['epoch'],'aliases':{name(a):known['aliases'].get(a) for a in aliases},'complete':True}

    def bind_alias(self,ref,alias):
        return self.rename(ref,alias)

    def _read(self,c,data,rr):
        self._ready(data)
        require(data.execute("SELECT value FROM meta WHERE key='generation'").fetchone()[0]==self.generation,'generation_mismatch')
        ok,reason=self._valid(c,rr)
        if not ok:return {'allowed':False,'ref':rr,'reason':reason}
        row=self._object(c,rr)
        content=data.execute('SELECT content FROM content WHERE ref=?',(key(rr),)).fetchone()
        if content is None:return {'allowed':False,'ref':rr,'reason':'content_missing'}
        require(digest(content[0])==row['content_sha256'],'content_digest_mismatch')
        alias=c.execute('SELECT alias FROM heads WHERE workspace=? AND artifact_id=?',(rr['workspace'],rr['artifact_id'])).fetchone()[0]
        return {'allowed':True,'ref':rr,'content':content[0],'content_sha256':row['content_sha256'],'reason':'allowed','alias':alias}

    def read(self,ref):
        rr=globals()['ref'](ref)
        try:
            with self.authority.transaction() as c, connect(self.path,True) as data:
                return self._read(c,data,rr)
        except (OSError,sqlite3.Error,MemoryError,ValueError):
            return {'allowed':False,'ref':rr,'reason':'authority_or_store_unavailable'}

    def validate(self,refs):
        require(type(refs) is list and len(refs)<=256,'invalid_batch')
        rs=[ref(r) for r in refs]
        try:
            with self.authority.transaction() as c, connect(self.path,True) as data:
                return {'decisions':[self._read(c,data,r) for r in rs]}
        except (OSError,sqlite3.Error,MemoryError,ValueError):
            return {'decisions':[{'allowed':False,'ref':r,'reason':'authority_or_store_unavailable'} for r in rs]}

    def search(self,workspace,query,limit=20):
        name(workspace);require(type(query) is str and len(query)<=4096,'invalid_query')
        require(type(limit) is int and 0<limit<=100,'invalid_limit')
        tokens=re.findall(r'\w+',query.casefold())
        with self.authority.transaction() as c, connect(self.path,True) as data:
            refs=[Ref(workspace,r[0],r[1]).to_dict() for r in c.execute('SELECT artifact_id,version_id FROM heads WHERE workspace=?',(workspace,))]
            results=[]
            for rr in refs:
                v=self._read(c,data,rr)
                if v['reason']=='content_missing':raise MemoryError('content_missing')
                if v['allowed']:
                    words=re.findall(r'\w+',v['content'].casefold())
                    score=sum(words.count(t) for t in tokens)
                    if score:results.append({**v,'score':score})
            return sorted(results,key=lambda x:(-x['score'],key(x['ref'])))[:limit]

    def context(self,workspace,query,limit=5):
        return {'items':self.search(workspace,query,limit),'policy':'single_authority_snapshot'}

    def plan_revocation(self,workspace,source_id):
        name(workspace);name(source_id)
        with self.authority.transaction() as c:
            objects=list(c.execute('SELECT * FROM objects WHERE workspace=?',(workspace,)))
            affected={canonical(Ref(workspace,r['artifact_id'],r['version_id']).to_dict()) for r in objects if r['artifact_id']==source_id}
            changed=True
            while changed:
                changed=False
                for r in objects:
                    k=key(Ref(workspace,r['artifact_id'],r['version_id']))
                    if k not in affected and any(d['relation'] in DEPENDENCIES and key(d['ref']) in affected for d in json.loads(r['dependencies'])):
                        affected.add(k);changed=True
            incomplete=any(not r['provenance_known'] for r in objects)
            return {'workspace':workspace,'source_id':source_id,'affected':[json.loads(k) for k in sorted(affected)],'coverage':'incomplete' if incomplete or not affected else 'known_dependencies_only'}

    def revoke_source(self,workspace,source_id,event_id):
        name(workspace);name(source_id);name(event_id)
        payload={'op':'revoke','workspace':workspace,'source_id':source_id,'event_id':event_id}
        with self.authority.transaction(True) as c:
            prior=c.execute('SELECT * FROM requests WHERE event_id=?',(event_id,)).fetchone()
            if prior:
                require(prior['payload']==canonical(payload),'event_id_conflict')
                seq=prior['seq']
            else:
                seq=self.authority.event(c,payload)
                c.execute('INSERT OR IGNORE INTO revoked VALUES (?,?,?,?)',(workspace,source_id,event_id,seq))
                c.execute('INSERT INTO requests VALUES (?,?,?)',(event_id,canonical(payload),seq))
            return {'event_id':event_id,'epoch':seq,'registered':True,'covered_reads_blocked':True,'projection_purge':'pending','coverage':'known_dependencies_only','physical_erasure':False}

    def get_revocation(self,event_id):
        with self.authority.transaction() as c:
            r=c.execute('SELECT * FROM requests WHERE event_id=?',(event_id,)).fetchone()
            require(r is not None,'unknown_event')
            pending=c.execute('SELECT delivered FROM outbox WHERE seq=?',(r['seq'],)).fetchone()[0]==0
            return {'event_id':event_id,'epoch':r['seq'],'registered':True,'covered_reads_blocked':True,'projection_purge':'pending' if pending else 'local_projection_reconciled','physical_erasure':False}

    def set_status(self,ref,status):
        rr=globals()['ref'](ref);require(status in STATES,'invalid_status')
        with self.authority.transaction(True) as c:
            require(self._object(c,rr) is not None,'unknown_ref')
            c.execute('UPDATE objects SET status=? WHERE workspace=? AND artifact_id=? AND version_id=?',(status,*rr.values()))
            return {'epoch':self.authority.event(c,{'op':'status','ref':rr,'status':status})}

    def explain_artifact(self,ref):
        rr=globals()['ref'](ref)
        with self.authority.transaction() as c:
            found={};stack=[rr]
            while stack:
                r=stack.pop();k=key(r)
                if k in found:continue
                require(len(found)<10000,'graph_limit')
                row=self._object(c,r);ok,reason=self._valid(c,r)
                node={'ref':r,'allowed':ok,'reason':reason,'dependencies':json.loads(row['dependencies']) if row else [],'provenance_known':bool(row['provenance_known']) if row else False}
                if row:
                    event=json.loads(c.execute('SELECT payload FROM events WHERE seq=?',(row['epoch'],)).fetchone()[0])
                    producer=event.get('producer')
                    node['producer']={k:v for k,v in producer.items() if k!='config'} if producer else None
                    node['retention']={'policy':'manual_indefinite','automatic_physical_purge':False}
                found[k]=node
                stack.extend(d['ref'] for d in node['dependencies'])
            return {'root':rr,'nodes':list(found.values()),'coverage':'known_dependencies_only'}

    @staticmethod
    def point_id(ref,model='lexical-v1',fragment='0'):
        name(model);name(fragment)
        return str(uuid.uuid5(uuid.NAMESPACE_URL,canonical({'ref':globals()['ref'](ref),'model':model,'fragment':fragment})))

    def project(self,ref,namespace='hermes-memory:lexical-v1',expected_epoch=None):
        rr=globals()['ref'](ref);name(namespace)
        require(namespace.startswith('hermes-memory:'),'foreign_namespace')
        with self.authority.transaction(True) as c:
            cp=self.authority._checkpoint(c)
            if expected_epoch is not None:require(type(expected_epoch) is int and expected_epoch==cp['epoch'],'stale_epoch')
            ok,reason=self._valid(c,rr);require(ok,reason)
            with connect(self.path) as data:
                self._ready(data)
                row=data.execute('SELECT content FROM content WHERE ref=?',(key(rr),)).fetchone()
                require(row is not None and digest(row[0])==self._object(c,rr)['content_sha256'],'content_missing_or_changed')
                pid=self.point_id(rr,namespace)
                data.execute('INSERT INTO projection VALUES (?,?,?,?,?) ON CONFLICT(namespace,point_id) DO UPDATE SET ref=excluded.ref,epoch=excluded.epoch,content=excluded.content WHERE excluded.epoch>=projection.epoch',(namespace,pid,key(rr),cp['epoch'],row[0]))
                return {'point_id':pid,'ref':rr,'epoch':cp['epoch']}

    def projection_search(self,workspace,query,namespace='hermes-memory:lexical-v1'):
        name(workspace);require(type(query) is str,'invalid_query')
        with self.authority.transaction() as authority, connect(self.path,True) as data:
            self._ready(data)
            candidates=[json.loads(r[0]) for r in data.execute('SELECT ref FROM projection WHERE namespace=?',(namespace,))]
            results=[]
            for r in candidates:
                if r['workspace']!=workspace:continue
                v=self._read(authority,data,r)
                if v['reason']=='content_missing':raise MemoryError('content_missing')
                if v['allowed'] and query.casefold() in v['content'].casefold():results.append(v)
            return results

    def reconcile(self,apply=False,namespace='hermes-memory:lexical-v1'):
        require(type(apply) is bool,'invalid_apply')
        require(namespace.startswith('hermes-memory:'),'foreign_namespace')
        with self.authority.transaction(True) as c, connect(self.path) as data:
            changes=[]
            for row in data.execute('SELECT * FROM projection WHERE namespace=?',(namespace,)).fetchall():
                ok,reason=self._valid(c,json.loads(row['ref']))
                if not ok:
                    changes.append({'action':'delete','point_id':row['point_id'],'reason':reason})
                    if apply:data.execute('DELETE FROM projection WHERE namespace=? AND point_id=?',(namespace,row['point_id']))
            return {'namespace':namespace,'applied':apply,'changes':changes}

    def drain_outbox(self,fail_after_projection=False):
        # Replay is safe: project is an upsert, purge is scoped, read validation independent.
        with self.authority.transaction() as c:
            pending=[dict(r) for r in c.execute('SELECT * FROM outbox WHERE delivered=0 ORDER BY seq')]
        count=0
        for row in pending:
            p=json.loads(row['payload'])
            if p['op']=='put':
                decision=self.read(p['ref'])
                if decision['allowed']:self.project(p['ref'])
                elif decision['reason'] not in {'source_revoked','version_not_current','archived','expired','invalidated','provenance_unknown'}:
                    raise MemoryError('projection_source_unavailable')
            with connect(self.path,True) as data:
                namespaces=[r[0] for r in data.execute("SELECT DISTINCT namespace FROM projection WHERE namespace LIKE 'hermes-memory:%'")]
            for namespace in namespaces:self.reconcile(apply=True,namespace=namespace)
            if fail_after_projection:raise MemoryError('injected_after_projection_before_ack')
            with self.authority.transaction(True) as c:
                c.execute('UPDATE outbox SET delivered=1 WHERE seq=?',(row['seq'],))
            count+=1
        return {'delivered':count}

    def backup(self,path):
        p=reserve(path)
        with self.authority.transaction() as authority, connect(self.path,True) as source, connect(p) as dest:
            source.backup(dest)
            dest.execute("UPDATE meta SET value='quarantine' WHERE key='mode'")
            cp=self.authority._checkpoint(authority)
            dest.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',('snapshot_checkpoint',canonical(cp)))
        return {'path':str(p),'quarantined':True,'checkpoint':cp}

    def restore_verify(self,expected_checkpoint):
        with self.authority.transaction(True) as c, connect(self.path) as data:
            cp=self.authority._checkpoint(c)
            require(type(expected_checkpoint) is dict and expected_checkpoint==cp,'restore_fresh_checkpoint_required')
            require(data.execute('PRAGMA integrity_check').fetchone()[0]=='ok','snapshot_integrity_failed')
            missing=[];blocked=[]
            for row in c.execute('SELECT * FROM heads'):
                r=Ref(row['workspace'],row['artifact_id'],row['version_id']).to_dict()
                ok,reason=self._valid(c,r)
                content=data.execute('SELECT content FROM content WHERE ref=?',(key(r),)).fetchone()
                if ok and (not content or digest(content[0])!=self._object(c,r)['content_sha256']):missing.append(r)
                elif not ok:blocked.append({'ref':r,'reason':reason})
            # Missing current versions remain explicitly unavailable; never fall back to old ones.
            for row in data.execute('SELECT namespace,point_id,ref FROM projection').fetchall():
                if row['namespace'].startswith('hermes-memory:') and not self._valid(c,json.loads(row['ref']))[0]:
                    data.execute('DELETE FROM projection WHERE namespace=? AND point_id=?',(row['namespace'],row['point_id']))
            data.execute("UPDATE meta SET value='ready' WHERE key='mode'")
            return {'ready':True,'checkpoint':cp,'missing_current_content':missing,'blocked':blocked,'coverage':'known_dependencies_only'}

    def import_markdown(self,workspace,source_id,path,expected_version=None):
        p=Path(path)
        require(p.is_file() and p.stat().st_size<=1024*1024,'invalid_markdown')
        content=p.read_text(encoding='utf-8')
        # Caller explicitly admits source; legacy derivation not fabricated.
        return self.register_source(workspace,source_id,content,alias=str(p),expected_version=expected_version)

    def compile_with(self,workspace,artifact_id,inputs,compiler,config=None,expected_version=None):
        config={} if config is None else dict(config)
        require(type(inputs) is list and 0<len(inputs)<=64,'invalid_compiler_inputs')
        inputs=[ref(r) for r in inputs]
        cp=self.checkpoint();values=self.validate(inputs)['decisions']
        require(all(v['allowed'] for v in values),'compiler_input_ineligible')
        content=compiler.compile([v['content'] for v in values],config)
        producer={'schema_version':1,'compiler_id':name(compiler.compiler_id),'compiler_version':name(compiler.compiler_version),'config':config,'config_sha256':digest(canonical(config)),'input_refs':inputs}
        return self.derive(workspace,artifact_id,content,'wiki',[{'ref':r,'relation':'derives'} for r in inputs],cp['epoch'],expected_version,producer=producer)

    def compile_deterministic(self,workspace,artifact_id,inputs,expected_version=None):
        from .compiler import DeterministicCompiler
        return self.compile_with(workspace,artifact_id,inputs,DeterministicCompiler(),expected_version=expected_version)
