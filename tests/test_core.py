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
        with sqlite3.connect(self.authority.path) as c:
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
        with sqlite3.connect(self.authority.path) as c:
            c.execute('UPDATE objects SET dependencies=? WHERE artifact_id=?',('[]','F'))
        self.assertFalse(self.m.read(f)['allowed'])

    def test_status_alias_head_materialization_cannot_downgrade(self):
        self.m.rename(self.A,'new.md')
        with sqlite3.connect(self.authority.path) as c:
            c.execute('DELETE FROM aliases WHERE alias=?',('a.md',))
        self.assertFalse(self.m.read(self.B)['allowed'])

    def test_mcp_cannot_override_read_operation(self):
        s=MCPSession(self.m)
        s.handle({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{}}})
        s.handle({'jsonrpc':'2.0','method':'notifications/initialized'})
        response=s.handle({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'memory_read','arguments':{'op':'revoke_source','workspace':'w','source_id':'A','event_id':'oops'}}})
        self.assertIn('error',response);self.assertTrue(self.m.read(self.A)['allowed'])

if __name__=='__main__':unittest.main()
