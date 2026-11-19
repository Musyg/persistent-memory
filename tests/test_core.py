from contextlib import closing
import concurrent.futures
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from hermes_memory import Authority,Memory,MemoryError
from hermes_memory.interfaces import MCPSession

class CoreScenarios(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.authority=Authority.create(self.root/'retained/authority.db',self.root/'anchor/checkpoint.json')
        self.m=Memory.create(self.root/'content.db',self.authority)
        self.A=self.m.register_source('w','A','alpha','a.md')['ref']
        self.B=self.m.register_source('w','B','beta','b.md')['ref']
    def tearDown(self):self.temp.cleanup()
    def derived(self,id='F',parents=None):
        return self.m.derive('w',id,'alpha beta','fact',[{'ref':r,'relation':'derives'} for r in (parents or [self.A])],self.m.checkpoint()['epoch'])['ref']
    def test_source_admission_keeps_integrity_without_redundant_epoch_scan(self):
        before=self.authority.checkpoint()
        with patch.object(self.authority,'_checkpoint',wraps=self.authority._checkpoint) as checkpoints:
            source=self.m.register_source('w','scan-source','synthetic gamma')
            # The ledger is unchanged since the last complete replay, so the start of the
            # transaction reuses it; event() reads the tail; the commit replays everything.
            self.assertEqual([c.kwargs.get('verify_state',True) for c in checkpoints.call_args_list],[True])
        self.assertEqual(source['epoch'],before['epoch']+1)
        self.assertEqual(self.m.read(source['ref'])['content'],'synthetic gamma')
        dependencies=[{'ref':source['ref'],'relation':'derives'}]
        # A None epoch is already an admitted derive contract; preserve it.
        with patch.object(self.authority,'_checkpoint',wraps=self.authority._checkpoint) as checkpoints:
            optional=self.m.derive('w','scan-optional','synthetic optional','lesson',dependencies,None)
            self.assertEqual([c.kwargs.get('verify_state',True) for c in checkpoints.call_args_list],[True])
        self.assertTrue(self.m.read(optional['ref'])['allowed'])
        epoch=self.authority.checkpoint()['epoch']
        with patch.object(self.authority,'_checkpoint',wraps=self.authority._checkpoint) as checkpoints:
            derived=self.m.derive('w','scan-required','synthetic derived','lesson',dependencies,epoch)
            self.assertEqual([c.kwargs.get('verify_state',True) for c in checkpoints.call_args_list],[True,True])
        self.assertEqual(derived['epoch'],epoch+1)
        self.assertEqual(self.m.read(derived['ref'])['content'],'synthetic derived')
        with self.assertRaisesRegex(MemoryError,'stale_epoch'):
            self.m.derive('w','scan-stale','must not publish','lesson',dependencies,epoch)
        self.assertEqual(self.authority.checkpoint()['epoch'],derived['epoch'])
        # A redundant inner scan is removed, not the transaction integrity gate.
        with closing(sqlite3.connect(self.m.path)) as data, data:
            content_count=data.execute('SELECT COUNT(*) FROM content').fetchone()[0]
        with closing(sqlite3.connect(self.authority.path)) as authority, authority:
            authority.execute('UPDATE objects SET content_sha256=? WHERE artifact_id=?',('0'*64,'scan-source'))
        with self.assertRaisesRegex(MemoryError,'authority_state_mismatch'):
            self.m.register_source('w','scan-blocked','must not persist')
        with closing(sqlite3.connect(self.m.path)) as data, data:
            self.assertEqual(data.execute('SELECT COUNT(*) FROM content').fetchone()[0],content_count)
        with closing(sqlite3.connect(self.authority.path)) as authority, authority:
            self.assertEqual(authority.execute('SELECT MAX(seq) FROM events').fetchone()[0],derived['epoch'])
    def test_incremental_verification_replays_whenever_the_ledger_may_have_changed(self):
        import hermes_memory.core as core
        now=[1000.0]
        clock=patch.object(core.time,'monotonic',side_effect=lambda:now[0]);clock.start();self.addCleanup(clock.stop)
        self.authority.checkpoint()
        def replays(fn):
            with patch.object(self.authority,'_checkpoint',wraps=self.authority._checkpoint) as checkpoints:
                fn()
            return len(checkpoints.call_args_list)
        # Unchanged file, recent complete replay: the checkpoint is served without a replay.
        self.assertEqual(replays(self.authority.checkpoint),0)
        self.assertEqual(replays(lambda:self.m.read(self.A)),0)
        # The periodic complete replay still happens once the interval has passed.
        now[0]+=core.FULL_VERIFY_SECONDS+1
        self.assertEqual(replays(self.authority.checkpoint),1)
        self.assertEqual(replays(self.authority.checkpoint),0)
        # A clock that went backwards is not trusted either.
        now[0]-=5
        self.assertEqual(replays(self.authority.checkpoint),1)
        # Interval 0: every transaction replays.
        with patch.object(core,'FULL_VERIFY_SECONDS',0):
            self.assertEqual(replays(lambda:self.m.read(self.A)),1)
            self.assertEqual(replays(lambda:self.m.read(self.A)),1)
        # Our own commit is recognised: the next read does not replay again.
        self.m.register_source('w','C','gamma')
        self.assertEqual(replays(self.authority.checkpoint),0)
        # A rolled-back transaction forgets the last replay.
        with self.assertRaises(RuntimeError):
            with self.authority.transaction(True):
                raise RuntimeError('abort')
        self.assertEqual(replays(self.authority.checkpoint),1)
        self.assertEqual(replays(self.authority.checkpoint),0)
        # A second Authority on the same file commits: the change counter moves, so the
        # first one replays on its next read instead of trusting its cache.
        other_authority=Authority.open(self.authority.path,self.authority.anchor_path)
        Memory.open(self.m.path,other_authority).register_source('w','D','delta')
        self.assertEqual(replays(self.authority.checkpoint),1)
        self.assertEqual(self.authority.checkpoint(),other_authority.checkpoint())
        # A commit by any other connection moves the change counter: the very next read
        # replays the ledger and refuses the tampered state despite the recent replay.
        with closing(sqlite3.connect(self.authority.path)) as other, other:
            other.execute("UPDATE objects SET status='archived' WHERE artifact_id='A'")
        with self.assertRaisesRegex(MemoryError,'authority_state_mismatch'):
            self.authority.checkpoint()
        self.assertEqual(self.m.read(self.B)['reason'],'authority_or_store_unavailable')
    def tamper(self,sql,*args):
        with closing(sqlite3.connect(self.authority.path)) as other, other:
            other.execute(sql,args)
    def test_cache_is_dropped_when_tail_or_generation_differ(self):
        # Even if the file signature looked unchanged, a new ledger tail or generation forces a replay.
        self.authority.checkpoint()
        with patch.object(self.authority,'_signature',side_effect=lambda c:(0,0,0)):
            self.authority.checkpoint()
            other=Authority.open(self.authority.path,self.authority.anchor_path)
            Memory.open(self.m.path,other).register_source('w','E','epsilon')
            self.assertEqual(self.authority.checkpoint(),other.checkpoint())
            self.tamper("UPDATE meta SET value='forged' WHERE key='generation'")
            with self.assertRaisesRegex(MemoryError,'anchor_mismatch'):
                self.authority.checkpoint()
    def test_a_commit_slipped_in_after_ours_is_not_cached(self):
        # Another writer commits between our commit and our second look at the file: the
        # counter moved by two, so the next read replays and sees the forged row.
        import hermes_memory.core as core
        real=core.atomic_json
        def forge(path,data):
            real(path,data)
            self.tamper("UPDATE objects SET status='archived' WHERE artifact_id='A'")
        with patch.object(core,'atomic_json',side_effect=forge):
            self.m.register_source('w','G','eta')
        with self.assertRaisesRegex(MemoryError,'authority_state_mismatch'):
            self.authority.checkpoint()
    def test_wal_journal_is_never_cached(self):
        # In WAL mode SQLite does not move the header change counter on commit.
        with closing(sqlite3.connect(self.authority.path)) as other:
            self.assertEqual(other.execute('PRAGMA journal_mode=WAL').fetchone()[0],'wal')
        self.authority.checkpoint()
        self.tamper("UPDATE objects SET status='archived' WHERE artifact_id='A'")
        with self.assertRaisesRegex(MemoryError,'authority_state_mismatch'):
            self.authority.checkpoint()
    def test_full_verify_interval_setting(self):
        import hermes_memory.core as core
        self.assertEqual(core._full_verify_seconds('5'),5.0)
        self.assertEqual(core._full_verify_seconds('0'),0.0)
        for bad in ('','soixante','-1',None):
            self.assertEqual(core._full_verify_seconds(bad),60.0)
    def test_mixed_and_independent_after_restore(self):
        f=self.derived(parents=[self.A,self.B]);self.m.backup(self.root/'old.db')
        self.m.revoke_source('w','A','r1');old=Memory.open(self.root/'old.db',self.authority)
        self.assertFalse(old.read(self.B)['allowed']);old.restore_verify(self.authority.checkpoint())
        self.assertFalse(old.read(f)['allowed']);self.assertTrue(old.read(self.B)['allowed'])
    def test_anchor_commit_gap_fails_closed_then_explicit_repair(self):
        old=self.authority.checkpoint()
        with patch('hermes_memory.core.atomic_json',side_effect=OSError('injected anchor outage')):
            with self.assertRaises(OSError):self.m.revoke_source('w','A','anchor-gap')
        self.assertFalse(self.m.read(self.B)['allowed'])
        with closing(sqlite3.connect(self.authority.path)) as c, c:
            c.row_factory=sqlite3.Row;trusted=self.authority._checkpoint(c)
        self.assertGreater(trusted['epoch'],old['epoch'])
        self.authority.recover_anchor(trusted)
        self.assertTrue(self.m.read(self.B)['allowed']);self.assertFalse(self.m.read(self.A)['allowed'])
    def test_compilation_late_epoch(self):
        epoch=self.m.checkpoint()['epoch'];self.m.revoke_source('w','A','r1')
        with self.assertRaises(MemoryError):self.m.derive('w','late','alpha','wiki',[{'ref':self.A,'relation':'derives'}],epoch)
    def test_concurrent_updates_one_winner(self):
        def change(value):
            try:return self.m.register_source('w','A',value,expected_version=self.A['version_id'])
            except (MemoryError,sqlite3.Error):return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            result=list(pool.map(change,['one','two']))
        self.assertEqual(sum(v is not None for v in result),1)
        self.assertFalse(self.m.read(self.A)['allowed'])
    def test_outbox_commit_projection_crash_replayed(self):
        f=self.derived()
        with self.assertRaises(MemoryError):self.m.drain_outbox(fail_after_projection=True)
        self.m.drain_outbox();self.m.drain_outbox()
        self.assertEqual(len(self.m.projection_search('w','alpha')),2)
        self.m.project(f,namespace='hermes-memory:second')
        self.m.revoke_source('w','A','r1');self.m.drain_outbox()
        self.assertEqual(self.m.projection_search('w','alpha',namespace='hermes-memory:second'),[])
    def test_citation_not_dependency(self):
        f=self.m.derive('w','cit','beta','wiki',[{'ref':self.B,'relation':'derives'},{'ref':self.A,'relation':'cites'}],self.m.checkpoint()['epoch'])['ref']
        self.m.revoke_source('w','A','r1');self.assertTrue(self.m.read(f)['allowed'])
    def test_alias_history_no_reuse_after_rename_revoke(self):
        self.m.rename(self.A,'new.md');self.m.revoke_source('w','A','r1')
        self.assertEqual(self.m.resolve('w','a.md')['ref'],self.A)
        with self.assertRaises(MemoryError):self.m.register_source('w','C','alpha','a.md')
    def test_fresh_version_not_resurrected_on_old_content(self):
        self.m.backup(self.root/'old.db')
        current=self.m.register_source('w','A','new',expected_version=self.A['version_id'])['ref']
        old=Memory.open(self.root/'old.db',self.authority);receipt=old.restore_verify(self.authority.checkpoint())
        self.assertIn(current,receipt['missing_current_content'])
        self.assertFalse(old.read(self.A)['allowed']);self.assertFalse(old.read(current)['allowed'])
        self.assertTrue(old.read(self.B)['allowed'])
    def test_repeated_compile_same_id(self):
        one=self.m.compile_deterministic('w','wiki',[self.A]);two=self.m.compile_deterministic('w','wiki',[self.A])
        self.assertEqual(one['ref'],two['ref']);self.assertEqual(one['epoch'],two['epoch'])
    def test_cross_workspace_rejected(self):
        with self.assertRaises(MemoryError):self.m.derive('other','wiki','alpha','wiki',[{'ref':self.A,'relation':'derives'}],self.m.checkpoint()['epoch'])
    def test_revoked_explain_contains_no_content(self):
        f=self.derived();self.m.revoke_source('w','A','r1');explain=self.m.explain_artifact(f)
        self.assertNotIn('alpha',json.dumps(explain));self.assertFalse(explain['nodes'][0]['allowed'])
    def test_compiler_receipt_exact_inputs_config_immutable(self):
        class Provider:
            compiler_id='test.fixed';compiler_version='2'
            def compile(self,texts,config):return config['prefix']+'|'.join(texts)
        v=self.m.compile_with('w','receipt',[self.A,self.B],Provider(),{'prefix':'synthetic:'})
        producer=self.m.explain_artifact(v['ref'])['nodes'][0]['producer']
        self.assertEqual(producer['input_refs'],[self.A,self.B])
        self.assertNotIn('config',producer)
        self.assertEqual(len(producer['config_sha256']),64)
        self.assertEqual(producer['compiler_version'],'2')
        self.assertTrue(self.m.read(v['ref'])['allowed'])
    def test_compiler_revocation_during_provider_rejects_publish(self):
        owner=self
        class Provider:
            compiler_id='test.revoke';compiler_version='1'
            def compile(self,texts,config):
                owner.m.revoke_source('w','A','during-provider')
                return 'withheld synthetic result'
        with self.assertRaises(MemoryError):self.m.compile_with('w','late-provider',[self.A],Provider())

    def test_corrupt_dependencies_cannot_bypass_ledger(self):
        f=self.derived()
        with closing(sqlite3.connect(self.authority.path)) as c, c:
            c.execute('UPDATE objects SET dependencies=? WHERE artifact_id=?',('[]','F'))
        self.assertFalse(self.m.read(f)['allowed'])

    def test_status_alias_head_materialization_cannot_downgrade(self):
        self.m.rename(self.A,'new.md')
        with closing(sqlite3.connect(self.authority.path)) as c, c:
            c.execute('DELETE FROM aliases WHERE alias=?',('a.md',))
        self.assertFalse(self.m.read(self.B)['allowed'])

    def test_mcp_cannot_override_read_operation(self):
        s=MCPSession(self.m)
        s.handle({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{}}})
        s.handle({'jsonrpc':'2.0','method':'notifications/initialized'})
        response=s.handle({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'memory_read','arguments':{'op':'revoke_source','workspace':'w','source_id':'A','event_id':'oops'}}})
        self.assertIn('error',response);self.assertTrue(self.m.read(self.A)['allowed'])

if __name__=='__main__':unittest.main()
