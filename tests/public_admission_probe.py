"""Independent installed-package probes. stdlib only; no candidate source inspection."""
import contextlib
import copy
import hashlib
import importlib
import importlib.util
import io
import itertools
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import types

HERE = Path(__file__).resolve().parent
SEED = json.loads((HERE / 'public_admission_seed.json').read_text(encoding='utf-8'))
ORACLE = json.loads((HERE / 'public_admission_oracle.json').read_text(encoding='utf-8'))
PUBLIC = {'A':'hermes_memory.admission','C':'hermes_memory.structured_memory','Q':'hermes_memory.quality_contract'}
RESERVED = ('hermes_memory._verified_admission_graph','_hermes_a1_pinned_c1','_hermes_c1_pinned_mechanical')
PINS = {'admission.py':'6fb7fd9a6eaecd0da2a50acd05ba253841da3ec41d904b324c8184720db43600',
        'structured_memory.py':'4febba12532671486bdb82e1eb39009cd7bb10206e33c10d46807e718da99697',
        'quality_contract.py':'0d16ebbf0042f03a5d6b36b1ed3b32b58e00945b73af1582f4bf2760492123b4'}
GROUPS = {
 'P01':['installed'],
 'P02':[''.join(p) for p in itertools.permutations('ACQ')],
 'P03':['ambient'] + ['reserved'+str(i) for i in range(3)] + ['plausible'],
 'P04':['missing-'+n for n in PINS] + ['changed-'+n for n in PINS] + ['missing-ambient','oversized','cached-change','cached-owner'],
 'P05':['one','four'], 'P06':['counter','bool','span','language'], 'P07':['unused'],
 'P08':['unknown','conflict','not_reviewed','malformed','exception'],
 'P09':['disclosed','hidden','conflict-denied','revision'],
 'P10':['added','added-denied','unknown-unchanged'],
 'P11':['exception','wrong-hash'], 'P12':['authority-mutation','sink-mutation']}
CHECKS = []
def require(name, value):
    CHECKS.append({'name':name,'passed':bool(value)})
    if not value: raise AssertionError(name)
def digest(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def installed_root():
    spec=importlib.util.find_spec('hermes_memory')
    require('installed_package_present',spec is not None and spec.origin is not None)
    root=Path(spec.origin).resolve().parent
    require('origin_below_active_interpreter_prefix',root.is_relative_to(Path(sys.prefix).resolve()))
    require('no_private_pythonpath',not os.environ.get('PYTHONPATH'))
    for name,pin in PINS.items():
        source=root/'_admission_sources'/name
        require('installed_raw_pin_'+name,source.is_file() and digest(source.read_bytes())==pin)
    return root
def load(order='ACQ'):
    modules={}
    for key in order: modules[key]=importlib.import_module(PUBLIC[key])
    return modules
def identity(modules):
    a,c,q=(modules[k] for k in 'ACQ')
    require('same_c1_render',a.admit.__globals__['_c1'].render is c.render)
    require('same_OutputContract',c.render.__globals__['_counter'].OutputContract is q.OutputContract)
    require('same_validate_output',c.render.__globals__['_counter'].validate_output is q.validate_output)
    require('canonical_contract_accepted',q.validate_output('un mot',q.OutputContract(1,10))['mechanical_pass'])
    for key,m in modules.items():require('repeat_import_identity_'+key,importlib.import_module(PUBLIC[key]) is m)
    graph=importlib.import_module('hermes_memory._admission_loader').load_graph()
    require('graph_admit_identity',graph.admit is a.admit)
    require('graph_sink_class_identity',graph.LabOrchestratorSink is a.LabOrchestratorSink)
    require('graph_canonical_identity',graph._c1.canonical is c.canonical)
    require('graph_counter_identity',graph._c1._counter.OutputContract is q.OutputContract)
    for name in ('ContractError','validate_output','make_initial_prompt','make_repair_prompt'):
        require('graph_counter_export_'+name,getattr(graph._c1._counter,name) is getattr(q,name))
def source_request(count=4, unused=False):
    sources=[];facts=[]
    for row in SEED['sources'][:count]:
        source=dict(id=row['id'],workspace=SEED['workspace'],version=row['version'],sha256=digest(row['text'].encode()),text=row['text'],state='active')
        sources.append(source)
        facts.append(dict(id=row['fact_id'],subject=SEED['subject'],property=row['property'],value=dict(type=row['value_type'],value=row['value']),unit=row['unit'],polarity=row['polarity'],scope=row['scope'],cardinality='single',source_id=source['id'],source_version=source['version'],source_sha256=source['sha256'],span=dict(start=0,end=len(source['text']),text=source['text']),origin='document',certainty='asserted'))
    if unused:
        row=SEED['unused_source'];sources.append(dict(row,sha256=digest(row['text'].encode())))
    ids=[f['id'] for f in facts]
    return dict(schema='hermes.structured.request.v1',workspace=SEED['workspace'],sources=sources,facts=facts,plan=dict(fact_ids=ids,required_ids=ids),contract=copy.deepcopy(SEED['c1_contract']))
def request(count=4,status='supported',unused=False):
    c1=source_request(count,unused)
    metadata=[{k:v for k,v in s.items() if k!='text'} for s in c1['sources']]
    needed=[s['id'] for s in c1['sources'][:count]] if status!='not_reviewed' else []
    return dict(schema='hermes.admission.request.v1',brief=SEED['brief'],accepts_format=True,workspace=SEED['workspace'],limits=copy.deepcopy(SEED['limits']),sources=metadata,dossier=dict(reviewer=None if status=='not_reviewed' else SEED['reviewer'],status=status,necessary_source_ids=needed),c1_request=c1 if status=='supported' else None)
def expected_body(count=4):
    sentences=[]
    for row in SEED['sources'][:count]:
        val='« '+row['value']+' »' if row['value_type']=='text' else row['value']
        unit='' if not row['unit'] else ' unité « '+row['unit']+' »'
        op='=' if row['polarity']=='positive' else '≠'
        sentences.append('« '+SEED['subject']+' » : « '+row['property']+' » '+op+' '+val+unit+' ; portée « '+row['scope']+' ». ['+row['id']+']')
    return ' '.join(sentences)
def prior_canaries():
    c1=source_request()
    values=[SEED['subject'],SEED['exception_canary'],digest(expected_body().encode())]
    for s in c1['sources']:values.extend((s['id'],s['version'],s['sha256'],s['text']))
    for f in c1['facts']:values.extend((f['id'],f['value']['value'],digest(canonical(f))))
    return values
def sanitized(result,delivered,stdout,stderr):
    enc=json.dumps([result,delivered,stdout,stderr],ensure_ascii=False)
    absent=all(value not in enc for value in prior_canaries())
    require('terminal_prior_canaries_absent',absent)
    e,r=result['envelope'],result['receipt']
    require('terminal_not_disclosed',e['evidence_review']==r['evidence_review']=='not_disclosed')
    require('terminal_revision_null',e['authority_revision'] is None and r['authority_revision'] is None)
    require('terminal_provenance_empty',r['provenance']==[])
    return {'all_prior_canaries_absent':absent}
def check_card(result,count):
    e,r=result['envelope'],result['receipt'];body=expected_body(count)
    require('admitted',e['decision']==r['decision']=='admitted')
    require('exact_compact_body',e['body']==body)
    require('technical_card',e['body_kind']=='technical_card')
    require('terminal_body_hash',e['body_sha256']==digest(body.encode()))
    c1=source_request(count);segments=body.split('] ')
    require('provenance_count',len(r['provenance'])==count)
    cursor=0
    for index,(p,f,s) in enumerate(zip(r['provenance'],c1['facts'],c1['sources'])):
        segment=segments[index]+(']' if index<count-1 else '')
        require('provenance_fact_'+str(index),p['fact_id']==f['id'] and p['fact_sha256']==digest(canonical(f)))
        require('provenance_source_'+str(index),p['source_id']==s['id'] and p['source_version']==s['version'] and p['source_sha256']==s['sha256'] and p['span']==f['span'])
        require('provenance_offsets_'+str(index),p['start']==cursor and p['end']==cursor+len(segment) and body[p['start']:p['end']]==segment and p['segment_sha256']==digest(segment.encode()))
        cursor+=len(segment)+1
def business(group,variant,modules):
    a,c,q=(modules[k] for k in 'ACQ')
    if group=='P06':
        if variant=='counter':
            for i,row in enumerate(SEED['counter_samples']):
                contract=q.OutputContract(1,100,allowed_citation_ids=['pub-src-n01'])
                report=q.validate_output(row['body'],contract)
                require('counter_'+str(i),report['word_count']==row['expected_words'] and report['semantic_status']=='not_evaluated')
            try:q.OutputContract(True,100)
            except q.ContractError:pass
            else:raise AssertionError('bool_contract_accepted')
            return {'category':'mechanical_counter','samples':2}
        rq=source_request(1)
        if variant=='bool':rq['contract']['max_candidates']=True
        if variant=='span':rq['facts'][0]['span']['text']='autre fragment'
        if variant=='language':rq['contract']['language']='en'
        calls=[]
        def authority_c1(snapshot,stage):calls.append(stage);return dict(status='allowed',revision='rights-c1')
        result=c.render(rq,authority_c1)
        expected='unsupported_scope' if variant=='language' else 'invalid_request'
        require('c1_failure_status',result['status']==expected and result['body']=='')
        require('c1_no_semantic_claim',result['semantic_status']=='not_evaluated' and result['publication_atomic'] is False)
        return {'category':'mechanical_refusal','status':result['status'],'authority_calls':len(calls)}
    count=1 if group=='P05' and variant=='one' else 4
    status=variant if group=='P08' and variant in ('unknown','conflict','not_reviewed') else 'supported'
    if group=='P09' and variant=='conflict-denied':status='conflict'
    if group=='P10' and variant=='unknown-unchanged':status='unknown'
    rq=request(count,status,unused=group=='P07')
    authority_calls=[];transform_calls=[];custom_deliveries=[]
    lab=a.LabOrchestratorSink()
    def authority(snapshot,stage):
        authority_calls.append(dict(stage=stage,snapshot=copy.deepcopy(snapshot)))
        if group=='P08' and variant=='malformed':return dict(status='allowed',revision=True,disclose_withdrawal=False)
        if group=='P08' and variant=='exception':raise RuntimeError(SEED['exception_canary'])
        if group=='P12' and variant=='authority-mutation' and stage=='before':
            rq['c1_request']['facts'][0]['value']['value']='9999'
            snapshot['sources'].clear()
        state='allowed';revision=SEED['stable_authority_revision'];disclose=False
        if stage=='before_handoff':
            if group=='P09':
                if variant in ('disclosed','hidden'):state='revoked';disclose=variant=='disclosed'
                elif variant=='conflict-denied':state='denied'
                elif variant=='revision':revision=SEED['changed_authority_revision']
            if group=='P10' and variant=='added-denied':state='denied'
        return dict(status=state,revision=revision,disclose_withdrawal=disclose)
    def transform(body):
        transform_calls.append(digest(body))
        return body+SEED['transform_addition'].encode() if group=='P10' and variant in ('added','added-denied') else body
    def custom_sink(envelope,receipt):
        custom_deliveries.append(dict(envelope=copy.deepcopy(envelope),receipt=copy.deepcopy(receipt)))
        old_hash=envelope['body_sha256']
        if group=='P11' and variant=='exception':raise RuntimeError(SEED['exception_canary'])
        if group=='P11' and variant=='wrong-hash':return dict(status='received',body_sha256='0'*64)
        envelope['body']='sink mutation';receipt['decision']='changed'
        return dict(status='received',body_sha256=old_hash)
    sink=custom_sink if group=='P11' or (group=='P12' and variant=='sink-mutation') else lab
    stdout=io.StringIO();stderr=io.StringIO()
    with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):result=a.admit(rq,authority,sink,transform)
    delivered=custom_deliveries if sink is custom_sink else lab.received
    calls=len(delivered) if sink is custom_sink else lab.calls
    require('no_application_console_output',stdout.getvalue()==stderr.getvalue()=='')
    require('not_atomic',result['envelope']['publication_atomic'] is False and result['receipt']['publication_atomic'] is False)
    require('no_extraction_claim',result['receipt']['extraction_measured'] is False)
    expected='admitted'
    if group=='P08':expected={'unknown':'unknown','conflict':'conflict','not_reviewed':'review_required','malformed':'authority_unavailable','exception':'authority_unavailable'}[variant]
    if group=='P09':expected={'disclosed':'withdrawn','hidden':'access_unavailable','conflict-denied':'access_unavailable','revision':'authority_changed'}[variant]
    if group=='P10':expected={'added':'consumer_changed','added-denied':'access_unavailable','unknown-unchanged':'unknown'}[variant]
    require('decision',result['envelope']['decision']==result['receipt']['decision']==expected)
    expected_calls=0 if expected=='consumer_changed' else 1
    require('sink_call_count',calls==expected_calls and len(delivered)==expected_calls)
    expected_auth=1 if group=='P08' and variant in ('malformed','exception') else 2
    require('authority_call_count',len(authority_calls)==expected_auth)
    require('authority_stages',[x['stage'] for x in authority_calls]==(['before'] if expected_auth==1 else ['before','before_handoff']))
    require('transform_call_count',len(transform_calls)==(0 if expected_auth==1 else 1))
    if expected=='admitted':check_card(result,count)
    elif expected=='consumer_changed':require('preventive_empty',result['envelope']['body']=='' and result['envelope']['body_kind']=='none' and result['envelope']['body_sha256'] is None)
    else:require('exact_notice',result['envelope']['body']==ORACLE['notices'][expected] and result['envelope']['body_kind']=='notice')
    require('handoff_attempt_count',result['handoff']['attempted']==expected_calls)
    if delivered:
        require('actual_sink_body_matches_terminal',delivered[0]['envelope']['body']==result['envelope']['body'] and delivered[0]['envelope']['body_sha256']==result['envelope']['body_sha256'])
        require('actual_sink_decision_matches_terminal',delivered[0]['receipt']['decision']==result['receipt']['decision'])
    if group=='P11':
        require('unknown_effect',result['handoff']['delivery']=='unknown' and result['envelope']['consumer_verified'] is False)
        require('sink_incident',result['handoff']['incident']==('sink_exception' if variant=='exception' else 'sink_hash_mismatch'))
    else:require('handoff_result',result['handoff']['delivery']==('acknowledged' if expected_calls else 'not_attempted') and result['handoff']['incident'] is None)
    if group=='P07':require('unused_not_authorized',all(SEED['unused_source']['id'] not in json.dumps(x) for x in authority_calls))
    if group=='P12' and variant=='authority-mutation':require('authority_snapshots_isolated',authority_calls[0]['snapshot']==authority_calls[1]['snapshot'])
    require('exception_detail_absent',SEED['exception_canary'] not in json.dumps([result,delivered],ensure_ascii=False))
    clean={}
    if expected in ('withdrawn','access_unavailable','authority_unavailable','authority_changed'):clean=sanitized(result,delivered,stdout.getvalue(),stderr.getvalue())
    category='unknown_sink_effect' if group=='P11' else 'factual_card' if expected=='admitted' else 'preventive_refusal' if expected=='consumer_changed' else 'notice'
    return dict(category=category,result=result,sink_calls=calls,delivered=delivered,authority_stages=[x['stage'] for x in authority_calls],transform_calls=len(transform_calls),canary_checks=clean)
def loader_failure(action,forbidden):
    try:action()
    except ImportError as exc:
        require('loader_error_generic',not any(x in str(exc) for x in forbidden))
        return
    raise AssertionError('loader_did_not_refuse')
def probe(group,variant):
    root=installed_root()
    with tempfile.TemporaryDirectory(prefix='public-boundary-') as temp:
        tmp=Path(temp)
        if group in ('P03','P04'):
            shutil.copytree(root,tmp/'hermes_memory')
            sys.path.insert(0,str(tmp))
            # find_spec has not imported the package; subsequent imports use only this disposable installed copy.
            root=tmp/'hermes_memory'
        trap='PUBLIC_LOADER_TRAP_Z8'
        import builtins
        setattr(builtins,trap,False)
        def trap_present():return getattr(builtins,trap)
        def add_ambient():
            for name in ('admission','structured_memory','quality_contract'):
                (tmp/(name+'.py')).write_text('import builtins\nbuiltins.'+trap+' = True\nraise RuntimeError("FOREIGN-CONTENT-Z8")\n',encoding='utf-8')
        if group=='P01':
            importlib.import_module('hermes_memory')
            require('opt_in_not_default',not any(name in sys.modules for name in (*PUBLIC.values(),*RESERVED,'hermes_memory._admission_loader')))
            identity(load())
            return {'category':'installed_import','installed':True}
        if group=='P02':identity(load(variant));return {'category':'identity','order':variant}
        if group=='P03':
            if variant=='ambient':add_ambient();identity(load());require('ambient_not_executed',not trap_present())
            else:
                index=0 if variant=='plausible' else int(variant[-1]);name=RESERVED[index]
                fake=types.ModuleType(name);fake.__file__=str(root/'_admission_sources'/'admission.py');fake.__package__='hermes_memory'
                fake.admit=lambda *a,**k:(_ for _ in ()).throw(AssertionError('foreign_used'))
                sys.modules[name]=fake
                loader_failure(lambda:load(),[str(tmp),'FOREIGN-CONTENT-Z8'])
                require('foreign_reservation_untouched',sys.modules.get(name) is fake)
                require('failed_graph_registrations_clean',all(n==name or n not in sys.modules for n in RESERVED))
                del sys.modules[name]
                identity(load())
            return {'category':'collision_refusal_or_irrelevant_homonym','foreign_executed':False}
        if group=='P04':
            cached=variant.startswith('cached-')
            if cached:identity(load())
            if variant=='cached-owner':
                name=RESERVED[1];owned=sys.modules[name];fake=types.ModuleType(name);sys.modules[name]=fake
                helper=importlib.import_module('hermes_memory._admission_loader')
                loader_failure(helper.load_graph,[str(tmp)])
                require('cached_foreign_not_replaced',sys.modules[name] is fake)
                sys.modules[name]=owned;identity(load())
            else:
                name=variant.split('-',1)[1] if variant.startswith(('missing-','changed-')) and variant!='missing-ambient' else 'quality_contract.py'
                path=root/'_admission_sources'/name;original=path.read_bytes()
                if variant.startswith('missing-'):
                    path.unlink()
                    if variant=='missing-ambient':add_ambient()
                else:
                    suffix=('\nimport builtins\nbuiltins.'+trap+' = True\n').encode()
                    path.write_bytes(original+suffix+(b'x'*(65536) if variant=='oversized' else b''))
                action=importlib.import_module('hermes_memory._admission_loader').load_graph if cached else lambda:load()
                loader_failure(action,[str(tmp),'FOREIGN-CONTENT-Z8'])
                require('tampered_or_ambient_not_executed',not trap_present())
                if not cached:require('failed_graph_registrations_clean',all(n not in sys.modules for n in RESERVED))
                path.write_bytes(original)
                identity(load())
            return {'category':'integrity_refusal','mutation':variant,'recovered_after_restore':True}
        return business(group,variant,load())
def child_main():
    require('linux_only',sys.platform.startswith('linux'))
    group,variant=sys.argv[1:3];require('registered_variant',group in GROUPS and variant in GROUPS[group])
    network_calls=[]
    def blocked(*a,**k):network_calls.append('blocked');raise AssertionError('network_forbidden')
    old_socket=socket.socket;old_connect=socket.create_connection;old_popen=subprocess.Popen
    class GuardedSocket(old_socket):
        def __new__(cls,*a,**k):return blocked(*a,**k)
    socket.socket=GuardedSocket;socket.create_connection=blocked;subprocess.Popen=blocked
    outer_out=io.StringIO();outer_err=io.StringIO()
    try:
        with contextlib.redirect_stdout(outer_out),contextlib.redirect_stderr(outer_err):observation=probe(group,variant)
        require('network_calls_zero',not network_calls)
        require('import_console_empty',outer_out.getvalue()==outer_err.getvalue()=='')
        output=dict(group=group,variant=variant,passed=True,checks=CHECKS,observation=observation)
        code=0
    except BaseException as exc:
        output=dict(group=group,variant=variant,passed=False,checks=CHECKS,error_type=type(exc).__name__,failed_check=str(exc) if type(exc) is AssertionError else 'unexpected_probe_error')
        code=1
    finally:socket.socket=old_socket;socket.create_connection=old_connect;subprocess.Popen=old_popen
    print(json.dumps(output,ensure_ascii=True));return code
def run_group(group):
    rows=[]
    for variant in GROUPS[group]:
        env=dict(os.environ);env.pop('PYTHONPATH',None);env['PYTHONDONTWRITEBYTECODE']='1'
        p=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).resolve()),group,variant],cwd=tempfile.gettempdir(),env=env,capture_output=True,text=True,encoding='utf-8',timeout=20)
        try:row=json.loads(p.stdout)
        except (ValueError,TypeError):row=dict(group=group,variant=variant,passed=False,error_type='invalid_probe_json')
        row['child_returncode']=p.returncode;row['child_stderr_empty']=not p.stderr
        row['passed']=bool(row.get('passed') and p.returncode==0 and not p.stderr)
        rows.append(row)
    return rows
if __name__=='__main__':raise SystemExit(child_main())
