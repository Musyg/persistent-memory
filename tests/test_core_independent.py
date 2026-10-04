"""Independent synthetic acceptance probes against real standalone core."""
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
import urllib.request
import urllib.error
import selectors
import tempfile
import unittest
from unittest.mock import patch

import hermes_memory.core as core
from hermes_memory.core import Authority, Memory, MemoryError
from hermes_memory.interfaces import make_server, MCPSession


class CoreReview(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='synthetic-core-review-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.authority=Authority.create(self.root/'authority.sqlite',self.root/'anchor.json')
        self.memory=Memory.create(self.root/'memory.sqlite',self.authority)

    def source(self,identifier='A',workspace='w',content=None,alias=None):
        return self.memory.register_source(workspace,identifier,content or ('synthetic '+identifier),alias=alias)['ref']

    def derive(self,identifier,parents,kind='fact',content=None,**kwargs):
        return self.memory.derive('w',identifier,content or ('synthetic '+identifier),kind,
            [{'ref':p,'relation':'derives'} for p in parents],self.memory.checkpoint()['epoch'],**kwargs)['ref']

    def chain(self):
        a=self.source(); b=self.source('B')
        f=self.derive('F',[a]); w=self.derive('W',[f],kind='wiki');v=self.derive('V',[w],kind='vector')
        for r in (a,b,f,w,v):self.memory.project(r)
        return a,b,f,w,v

    def test_T01_T03_composed_transitive_chain_and_independent_B(self):
        a,b,f,w,v=self.chain()
        planned=self.memory.plan_revocation('w','A')
        self.assertEqual({r['artifact_id'] for r in planned['affected']},{'A','F','W','V'})
        receipt=self.memory.revoke_source('w','A','remove-A')
        self.assertTrue(receipt['covered_reads_blocked'])
        for r in (a,f,w,v):
            decision=self.memory.read(r)
            self.assertFalse(decision['allowed']);self.assertNotIn('content',decision)
        self.assertTrue(self.memory.read(b)['allowed'])
        self.assertEqual([v['ref']['artifact_id'] for v in self.memory.projection_search('w','synthetic')],['B'])

    def test_T02_mixed_source_suspended_then_rebuilt_from_B(self):
        a,b=self.source(),self.source('B')
        w=self.derive('mixed',[a,b],kind='wiki')
        self.memory.revoke_source('w','A','remove')
        self.assertFalse(self.memory.read(w)['allowed'])
        fresh=self.derive('mixed',[b],kind='wiki',expected_version=w['version_id'])
        self.assertTrue(self.memory.read(fresh)['allowed'])

    def test_T04_rename_keeps_exact_identity(self):
        a=self.source(alias='old/path.md');f=self.derive('F',[a])
        changed=self.memory.rename(a,'new/path.md')
        self.assertEqual(changed['ref'],a)
        self.assertEqual(self.memory.resolve('w','new/path.md')['ref'],a)
        self.assertTrue(self.memory.read(f)['allowed'])

    def test_T05_replacement_invalidates_old_dependencies(self):
        a=self.source();f=self.derive('F',[a])
        newer=self.memory.register_source('w','A','synthetic replacement',expected_version=a['version_id'])['ref']
        self.assertNotEqual(newer,a)
        self.assertFalse(self.memory.read(a)['allowed'])
        self.assertFalse(self.memory.read(f)['allowed'])
        self.assertTrue(self.memory.read(newer)['allowed'])

    def test_T06_T11_late_derivation_rejected(self):
        a=self.source();epoch=self.memory.checkpoint()['epoch']
        self.memory.revoke_source('w','A','withdraw')
        with self.assertRaises(MemoryError):
            self.memory.derive('w','late','synthetic late','wiki',[{'ref':a,'relation':'derives'}],epoch)

    def test_T08_outbox_crash_after_projection_replay_idempotent(self):
        self.chain()
        self.memory.revoke_source('w','A','withdraw')
        with self.assertRaises(MemoryError):self.memory.drain_outbox(fail_after_projection=True)
        reopened=Memory.open(self.memory.path,Authority.open(self.authority.path,self.authority.anchor_path))
        reopened.drain_outbox();reopened.drain_outbox()
        with sqlite3.connect(self.memory.path) as db:
            rows=db.execute('SELECT namespace,point_id,COUNT(*) FROM projection GROUP BY namespace,point_id').fetchall()
        self.assertTrue(all(r[2]==1 for r in rows))
        self.assertEqual([v['ref']['artifact_id'] for v in reopened.projection_search('w','synthetic')],['B'])

    def test_T09_duplicate_event_and_conflicting_reuse(self):
        self.source();self.source('B')
        a=self.memory.revoke_source('w','A','event')
        self.assertEqual(self.memory.revoke_source('w','A','event')['epoch'],a['epoch'])
        with self.assertRaises(MemoryError):self.memory.revoke_source('w','B','event')

    def test_T12_restore_old_content_with_current_authority(self):
        a,b,f,w,v=self.chain()
        backup=self.root/'old.sqlite';self.memory.backup(backup)
        self.memory.revoke_source('w','A','withdraw')
        restored=Memory.open(backup,self.authority)
        self.assertFalse(restored.read(b)['allowed'])
        receipt=restored.restore_verify(self.authority.checkpoint())
        self.assertTrue(receipt['ready'])
        for r in (a,f,w,v):self.assertFalse(restored.read(r)['allowed'])
        self.assertTrue(restored.read(b)['allowed'])
        self.assertEqual([v['ref']['artifact_id'] for v in restored.projection_search('w','synthetic')],['B'])

    def test_T13_stale_authority_against_current_anchor_refused(self):
        self.source();old=self.root/'old-authority.sqlite'
        shutil.copy2(self.authority.path,old)
        self.memory.revoke_source('w','A','withdraw')
        with self.assertRaises(MemoryError):Authority.open(old,self.authority.anchor_path)

    def test_T13_missing_anchor_not_recreated(self):
        self.source();self.authority.anchor_path.unlink()
        with self.assertRaises(MemoryError):Authority.open(self.authority.path,self.authority.anchor_path)
        self.assertFalse(self.authority.anchor_path.exists())

    def test_T13_checkpoint_from_old_snapshot_does_not_authorize_restore(self):
        self.source();oldcp=self.memory.backup(self.root/'old.sqlite')['checkpoint']
        self.memory.revoke_source('w','A','withdraw')
        restored=Memory.open(self.root/'old.sqlite',self.authority)
        with self.assertRaises(MemoryError):restored.restore_verify(oldcp)

    def test_T14_unknown_provenance_remains_explicit(self):
        r=self.memory.derive('w','legacy','synthetic old wiki','wiki',[],self.memory.checkpoint()['epoch'],provenance_known=False)['ref']
        explanation=self.memory.explain_artifact(r)
        self.assertFalse(explanation['nodes'][0]['provenance_known'])
        self.assertEqual(self.memory.plan_revocation('w','missing')['coverage'],'incomplete')

    def test_T16_scope_isolation_and_cross_scope_edges_refused(self):
        a=self.source('A','w');b=self.source('A','other')
        self.assertNotEqual(self.memory.point_id(a),self.memory.point_id(b))
        with self.assertRaises(MemoryError):self.derive('bad',[b])
        self.memory.revoke_source('w','A','withdraw')
        self.assertTrue(self.memory.read(b)['allowed'])

    def test_T17_archived_excluded_from_active_reads(self):
        a=self.source();self.memory.set_status(a,'archived')
        self.assertFalse(self.memory.read(a)['allowed'])
        self.assertEqual(self.memory.search('w','synthetic'),[])

    def test_T18_same_point_is_stable_and_upsert_idempotent(self):
        a=self.source()
        one=self.memory.project(a);two=self.memory.project(a)
        self.assertEqual(one['point_id'],two['point_id'])
        self.assertNotEqual(self.memory.point_id(a,'model1'),self.memory.point_id(a,'model2'))
        with sqlite3.connect(self.memory.path) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM projection').fetchone()[0],1)

    def test_T18_same_compilation_inputs_dont_create_unjustified_new_version(self):
        a=self.source()
        first=self.memory.compile_deterministic('w','wiki',[a])
        second=self.memory.compile_deterministic('w','wiki',[a],expected_version=first['ref']['version_id'])
        self.assertEqual(first['ref'],second['ref'])

    def test_R15_explanation_and_receipt_do_not_copy_revoked_text(self):
        secret='synthetic sensitive marker not a real secret'
        a=self.source(content=secret)
        self.memory.revoke_source('w','A','withdraw')
        text=json.dumps(self.memory.explain_artifact(a))+json.dumps(self.memory.get_revocation('withdraw'))
        self.assertNotIn(secret,text)

    def test_citation_does_not_invalidate_independent_generation(self):
        a,b=self.source(),self.source('B')
        r=self.memory.derive('w','wiki','synthetic B wiki','wiki',
            [{'ref':b,'relation':'derives'},{'ref':a,'relation':'cites'}],self.memory.checkpoint()['epoch'])['ref']
        self.memory.revoke_source('w','A','withdraw')
        self.assertTrue(self.memory.read(r)['allowed'])

    def test_new_namespace_projection_purge_progress_covers_its_claim(self):
        a=self.source();self.memory.project(a,namespace='hermes-memory:other-model')
        self.memory.revoke_source('w','A','withdraw');self.memory.drain_outbox()
        receipt=self.memory.get_revocation('withdraw')
        with sqlite3.connect(self.memory.path) as db:
            remaining=db.execute("SELECT COUNT(*) FROM projection WHERE namespace='hermes-memory:other-model'").fetchone()[0]
        self.assertTrue(remaining==0 or receipt['projection_purge']=='pending',
                        'must not claim local projection reconciled while another managed namespace remains')

    def test_T10_query_uses_one_authority_snapshot_then_revalidates_next_call(self):
        a,b=self.source(),self.source('B')
        original=self.memory._read;observed=[]
        def observed_read(connection,data,r):
            observed.append((id(connection),connection.in_transaction,r['artifact_id']))
            return original(connection,data,r)
        self.memory._read=observed_read
        results=self.memory.search('w','synthetic')
        self.assertEqual({v['ref']['artifact_id'] for v in results},{'A','B'})
        self.assertEqual(len({row[0] for row in observed}),1)
        self.assertTrue(all(row[1] for row in observed))
        self.assertEqual({row[2] for row in observed},{'A','B'})
        self.memory.revoke_source('w','A','withdraw')
        self.assertEqual({v['ref']['artifact_id'] for v in self.memory.search('w','synthetic')},{'B'})

    def test_positive_lexical_search_and_context_return_real_matches(self):
        a=self.source(content='violet synthetic telescope')
        self.assertEqual([x['ref'] for x in self.memory.search('w','telescope')],[a])
        self.assertEqual([x['ref'] for x in self.memory.context('w','telescope')['items']],[a])

    def test_missing_current_content_never_acks_outbox_or_returns_empty_search(self):
        a=self.source()
        with sqlite3.connect(self.memory.path) as db:db.execute('DELETE FROM content')
        self.assertFalse(self.memory.read(a)['allowed'])
        with self.assertRaises(MemoryError):self.memory.search('w','synthetic')
        with self.assertRaises(MemoryError):self.memory.drain_outbox()
        with sqlite3.connect(self.authority.path) as db:
            self.assertEqual(db.execute('SELECT SUM(delivered) FROM outbox').fetchone()[0],0)

    def cli(self,*args):
        return subprocess.run([sys.executable,'-B','-m','hermes_memory','--authority',str(self.authority.path),
            '--anchor',str(self.authority.anchor_path),'--store',str(self.memory.path),*args],
            text=True,capture_output=True,timeout=10)

    def test_T15_cli_matches_python_before_and_after_withdrawal(self):
        a=self.source()
        request=json.dumps({'op':'read','ref':a})
        before=self.cli('rpc',request)
        self.assertEqual(before.returncode,0,before.stderr)
        self.assertEqual(json.loads(before.stdout)['content'],self.memory.read(a)['content'])
        self.memory.revoke_source('w','A','withdraw')
        after=self.cli('rpc',request)
        self.assertEqual(after.returncode,0,after.stderr)
        self.assertFalse(json.loads(after.stdout)['allowed'])
        self.assertNotIn('content',json.loads(after.stdout))

    def test_T15_real_http_matches_python_and_rejects_validate_op_override(self):
        a=self.source();token='synthetic-test-token-0123456789abcdef'
        server=make_server(self.memory,'127.0.0.1',0,token=token)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base='http://127.0.0.1:'+str(server.server_port)
            def post(path,payload,authorized=True):
                headers={'Content-Type':'application/json'}
                if authorized:headers['Authorization']='Bearer '+token
                req=urllib.request.Request(base+path,data=json.dumps(payload).encode(),headers=headers)
                with urllib.request.urlopen(req,timeout=3) as response:return json.load(response)
            self.assertEqual(post('/rpc',{'op':'read','ref':a})['content'],self.memory.read(a)['content'])
            with self.assertRaises(urllib.error.HTTPError) as caught:
                post('/rpc',{'op':'read','ref':a},authorized=False)
            self.assertEqual(caught.exception.code,401)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                post('/validate',{'refs':[a],'op':'revoke_source','workspace':'w','source_id':'A','event_id':'bad'})
            self.assertEqual(caught.exception.code,400)
            self.assertTrue(self.memory.read(a)['allowed'])
            self.memory.revoke_source('w','A','withdraw')
            decision=post('/rpc',{'op':'read','ref':a})
            self.assertFalse(decision['allowed']);self.assertNotIn('content',decision)
        finally:
            server.shutdown();server.server_close();thread.join(3)

    def test_T15_real_mcp_stdio_handshake_tools_and_revoked_read(self):
        a=self.source()
        command=[sys.executable,'-B','-m','hermes_memory','--authority',str(self.authority.path),
                 '--anchor',str(self.authority.anchor_path),'--store',str(self.memory.path),'mcp']
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        def send(message,reply=True):
            process.stdin.write(json.dumps(message)+'\n');process.stdin.flush()
            if not reply:return None
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout,selectors.EVENT_READ)
                self.assertTrue(selector.select(3),'MCP response deadline')
            line=process.stdout.readline();self.assertTrue(line,'MCP EOF')
            return json.loads(line)
        try:
            init=send({'jsonrpc':'2.0','id':1,'method':'initialize','params':{
                'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'independent-review','version':'1'}}})
            self.assertEqual(init['result']['protocolVersion'],'2025-03-26')
            send({'jsonrpc':'2.0','method':'notifications/initialized'},False)
            tools=send({'jsonrpc':'2.0','id':2,'method':'tools/list'})
            self.assertIn('memory_read',[t['name'] for t in tools['result']['tools']])
            call={'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'memory_read','arguments':{'ref':a}}}
            first=send(call)['result'];self.assertFalse(first['isError'])
            self.assertTrue(json.loads(first['content'][0]['text'])['allowed'])
            self.memory.revoke_source('w','A','withdraw')
            call['id']=4
            last=send(call)['result'];decision=json.loads(last['content'][0]['text'])
            self.assertFalse(decision['allowed']);self.assertNotIn('content',decision)
        finally:
            process.stdin.close()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            process.stdout.close();process.stderr.close()

    def test_mcp_read_tool_cannot_change_operation(self):
        a=self.source();session=MCPSession(self.memory)
        session.handle({'jsonrpc':'2.0','id':1,'method':'initialize','params':{
            'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'synthetic','version':'1'}}})
        session.handle({'jsonrpc':'2.0','method':'notifications/initialized'})
        response=session.handle({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{
            'name':'memory_read','arguments':{'op':'revoke_source','workspace':'w','source_id':'A','event_id':'bad'}}})
        self.assertIn('error',response)
        self.assertTrue(self.memory.read(a)['allowed'])

    def test_authority_commit_then_anchor_failure_blocks_until_explicit_repair(self):
        a,b=self.source(),self.source('B');before=self.authority.checkpoint()
        with patch.object(core,'atomic_json',side_effect=OSError('synthetic anchor write fault')):
            with self.assertRaises(OSError):self.memory.revoke_source('w','A','withdraw')
        self.assertEqual(self.memory.read(a)['reason'],'authority_or_store_unavailable')
        self.assertFalse(self.memory.read(b)['allowed'])
        with self.assertRaises(MemoryError):self.authority.recover_anchor(before)
        # Independent inspection of the committed synthetic ledger models explicit operator audit.
        with core.connect(self.authority.path) as db:committed=self.authority._checkpoint(db)
        self.assertGreater(committed['epoch'],before['epoch'])
        self.authority.recover_anchor(committed)
        self.assertFalse(self.memory.read(a)['allowed'])
        self.assertTrue(self.memory.read(b)['allowed'])

    def test_projection_reconciliation_never_touches_foreign_namespace(self):
        a=self.source()
        with sqlite3.connect(self.memory.path) as db:
            db.execute('INSERT INTO projection VALUES (?,?,?,?,?)',('foreign:index','unchanged',core.key(a),1,'foreign synthetic copy'))
        self.memory.project(a);self.memory.revoke_source('w','A','withdraw');self.memory.drain_outbox()
        with sqlite3.connect(self.memory.path) as db:
            self.assertEqual(db.execute("SELECT content FROM projection WHERE namespace='foreign:index'").fetchone()[0],'foreign synthetic copy')

    def test_failed_alias_registration_cannot_publish_orphaned_content(self):
        self.source('A',alias='occupied')
        with self.assertRaises((MemoryError,sqlite3.IntegrityError)):
            self.memory.register_source('w','B','synthetic B orphan',alias='occupied')
        self.assertIsNone(self.memory.resolve('w','not-bound')['ref'])
        self.assertEqual([x['ref']['artifact_id'] for x in self.memory.search('w','synthetic')],['A'])

    def test_materialized_revocation_row_deleted_does_not_undo_ledger(self):
        a=self.source();self.memory.revoke_source('w','A','withdraw')
        with sqlite3.connect(self.authority.path) as db:db.execute('DELETE FROM revoked')
        decision=self.memory.read(a)
        self.assertFalse(decision['allowed'])
        self.assertEqual(decision['reason'],'authority_or_store_unavailable')
        with self.assertRaises(MemoryError):self.memory.search('w','synthetic')

    def test_materialized_archived_row_reactivated_fails_closed(self):
        a=self.source();self.memory.set_status(a,'archived')
        with sqlite3.connect(self.authority.path) as db:db.execute("UPDATE objects SET status='active'")
        self.assertFalse(self.memory.read(a)['allowed'])
        with self.assertRaises(MemoryError):self.authority.checkpoint()


if __name__=='__main__':
    unittest.main(verbosity=2)
