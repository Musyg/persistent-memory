"""Native Root supervision of the frozen cell plan through the existing benchmark CLI."""
import base64,concurrent.futures,ctypes,decimal,hashlib,json,os,pathlib,pwd,signal,subprocess,threading,time,traceback
def terminate_cell_group(process):
 """Kill the cell session and reap the parent and any adopted descendants."""
 try:os.killpg(process.pid,signal.SIGKILL)
 except ProcessLookupError:pass
 process.wait(timeout=10)
 deadline=time.monotonic()+10
 while True:
  while True:
   try:child,status=os.waitpid(-process.pid,os.WNOHANG)
   except ChildProcessError:break
   if child==0:break
  try:os.killpg(process.pid,0)
  except ProcessLookupError:return
  if time.monotonic()>deadline:raise RuntimeError('cell_group_not_reaped')
  time.sleep(.01)
lab=pathlib.Path(_LAB_);base=pathlib.Path(_BASE_);sha=lambda b:hashlib.sha256(b).hexdigest()
raw=(lab/'candidate.json').read_bytes();assert sha(raw)==_PIN_
manifest=json.loads(raw);expected=manifest['files'];admission=manifest['root_admission']
assert admission['schema']=='hermes.action-transfer.root-admission.v1'and admission['authorized_for_execution']is True
experience=admission['purpose']=='experience_transfer'
mode=admission.get('mode','paid');assert mode in('fake','paid')and(mode=='paid'or experience)
assert admission['max_requests']in((0,288)if experience else(48,576))and admission['concurrency']==3
assert decimal.Decimal(admission['macro_ceiling_USD'])==(0 if mode=='fake'else 8 if experience else 15)
assert decimal.Decimal(admission['prior_conservative_debit_USD'])+decimal.Decimal(admission['macro_ceiling_USD'])<=250
assert time.time()<admission['expires_at_epoch']
repo=lab/'repo';repo.mkdir(mode=0o700);overlays=json.loads((lab/'overlays.json').read_bytes())
for name,pin in expected.items():
 relative=pathlib.PurePosixPath(name);assert not relative.is_absolute()and'..'not in relative.parts and'\\'not in name
 body=base64.b64decode(overlays[name],validate=True)if name in overlays else(base/'repo'/name).read_bytes()
 assert len(body)==pin['bytes']and sha(body)==pin['sha256'],name
 out=repo/name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(body);out.chmod(0o444)
fixture_name=admission.get('fixture_relative_path','benchmarks/action-20261023/FIXTURE.json')
plan_name=admission.get('plan_relative_path','benchmarks/action-20261023/PLAN.json')
for name in(fixture_name,plan_name):
 relative=pathlib.PurePosixPath(name)
 assert not relative.is_absolute()and'..'not in relative.parts and'\\'not in name and name in expected
fixture_path=repo/fixture_name;fixture_raw=fixture_path.read_bytes()
plan_path=repo/plan_name;plan_raw=plan_path.read_bytes();plan=json.loads(plan_raw)
assert sha(fixture_raw)==admission['dataset_sha256']==plan['dataset_sha256']
full_count=288 if experience else 576
assert sha(plan_raw)==admission['plan_sha256']and len(plan['cells'])==full_count
selected_ids=admission['selected_cell_ids']
assert len(selected_ids)==len(set(selected_ids))==(72 if mode=='fake'else admission['max_requests'])
selected_set=set(selected_ids)
selected=[c for c in plan['cells']if c['cell_id']in selected_set]
assert [c['cell_id']for c in selected]==selected_ids
if experience:
 assert plan['schema']=='persistent-memory.experience-plan.v1'and len(plan['episodes'])==48
 episodes=[e for e in plan['episodes']if e['a_cell_id']in selected_set]
 assert len(episodes)==(12 if mode=='fake'else 48)
 assert {cid for e in episodes for cid in(e['a_cell_id'],e['extract_cell_id'],*e['b_cell_ids'].values())}==selected_set
 assert all(set(e['b_cell_ids'])=={'derived','raw','none','withdrawn'}for e in episodes)
elif admission['max_requests']==48:
 assert selected==[c for c in plan['cells']if c['arm']=='memory_on'and c['repetition']==1]
 assert len({(c['world_id'],c['model'])for c in selected})==48
 assert admission['purpose']=='known_fixture_interface_calibration'
else:
 assert selected==plan['cells']and admission['purpose']=='fresh_parameter_confirmation'
support=repo/'benchmarks/action_transfer.py';provider=repo/'benchmarks/validation-20261021/REPLAY/CODE/bounded_provider.py'
reader=repo/'benchmarks/validation-20261021/REPLAY/CODE/run_pilot.py';benchmark=repo/'benchmarks/run_benchmark.py'
for path,key in((support,'support_sha256'),(provider,'provider_sha256'),(reader,'credential_reader_sha256'),(benchmark,'benchmark_sha256')):
 assert sha(path.read_bytes())==admission[key]
outside=lab/'outside';outside.mkdir(mode=0o700);cells=lab/'cells';cells.mkdir(mode=0o700)
env={'PATH':os.defpath,'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','PIP_NO_INDEX':'1','PYTHONDONTWRITEBYTECODE':'1'}
baseline_python=base/'installed/hermes_memory-wheel/venv/bin/python'
subprocess.run([str(baseline_python),'-I','-B','-m','venv','--system-site-packages',str(lab/'venv')],env=env,cwd=outside,check=True,timeout=90,capture_output=True)
python=lab/'venv/bin/python';wheels=sorted((base/'repo/dist').glob('*/*.whl'));assert len(wheels)==2
subprocess.run([str(python),'-I','-B','-m','pip','install','--no-index','--no-deps',*[str(p)for p in wheels]],env=env,cwd=outside,check=True,timeout=90,capture_output=True)
site=list((lab/'venv/lib').glob('python*/site-packages'));assert len(site)==1
(site[0]/'admitted-readonly-httpx-dependencies.pth').write_text(admission['readonly_dependency_path']+'\n')
units={'gpt-6-luna':decimal.Decimal('0.0021504'),'gpt-6.1-sol':decimal.Decimal('0.043008')}
assert (sum((units[c['model']]for c in selected),decimal.Decimal(0))if mode=='paid'else decimal.Decimal(0))==decimal.Decimal(admission['planned_reservation_USD'])
# Only the new private lab changes owner. Never follow interpreter symlinks.
owner=pwd.getpwnam('hermes')
for path in lab.rglob('*'):
 assert path.is_relative_to(lab)
 os.chown(path,owner.pw_uid,owner.pw_gid,follow_symlinks=False)
os.chown(lab,owner.pw_uid,owner.pw_gid);os.setgroups([]);os.setgid(owner.pw_gid);os.setuid(owner.pw_uid)
assert os.geteuid()==admission['worker_uid']==1000 and os.getegid()==admission['worker_gid']==1000
assert ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0,'child_subreaper_required'
started=time.monotonic();stop=threading.Event();lock=threading.Lock();finished={}
def write_new(path,value):
 body=(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
 with path.open('xb')as out:out.write(body);out.flush();os.fsync(out.fileno())
 path.chmod(0o600);return sha(body)
def make_grant(cell,directory):
 profile_name='volume_luna6_none_v1'if cell['model']=='gpt-6-luna'else'volume_sol61_low_v1'
 unit=str(units[cell['model']]);effort='none'if cell['model']=='gpt-6-luna'else'low'
 profile={'schema_version':1,'profile':profile_name,'purpose':'generation','dataset_sha256':admission['dataset_sha256'],
  'cells':[{'cell_id':cell['cell_id'],'task_id':cell['world_id'],'stage':'rep'+str(cell['repetition']),'arm':cell['arm']}],
  'max_requests':1,'wall_seconds':300,'per_request_usd':unit,'max_total_usd':unit}
 budget={**profile,'authorized_for_execution':True,'price_verified':True,'tokenizer_bound_verified':True,'reasoning_total_bound_verified':True,
  'model':cell['model'],'endpoint':'https://api.openai.com/v1/chat/completions','request_options':{'reasoning_effort':effort},
  'response_models':[cell['model']],'input_tokens_per_request':11264,'output_tokens_per_request':2048,
  'full_request_bytes':10240,'message_bytes':10240,'framing_token_allowance':1024,'timeout_seconds':90,
  'expires_at_epoch':admission['expires_at_epoch']}
 budget_pin=write_new(directory/'budget.json',budget)
 grant={'schema':'persistent-memory.action-transfer.grant.v1','authorized_for_execution':True,
  'provider_sha256':admission['provider_sha256'],'support_sha256':admission['support_sha256'],
  'dataset_sha256':admission['dataset_sha256'],'cell_id':cell['cell_id'],'model':cell['model'],
  'expires_at_epoch':admission['expires_at_epoch'],'budget':{'path':'budget.json','sha256':budget_pin},'profile':profile,
  'credential':{'path':admission['credential_path'],'env_file':True,'field':'OPENAI_API_KEY'}}
 grant_pin=write_new(directory/'grant.json',grant)
 return grant_pin
def execute(cell):
 row={'cell':cell,'dataset_sha256':admission['dataset_sha256'],'plan_sha256':admission['plan_sha256'],
      'consume':None,'verification':None,'emission_status':'not_executed','terminal_category':'not_executed'}
 if stop.is_set():return row
 if time.time()>=admission['expires_at_epoch']or time.monotonic()-started>2100:
  stop.set();return row
 directory=cells/cell['cell_id'];directory.mkdir(mode=0o700)
 grant_pin=make_grant(cell,directory);output=directory/'run'
 command=[str(python),'-I','-B',str(benchmark),'--action-transfer','--action-fixture',str(fixture_path),
  '--action-fixture-sha256',admission['dataset_sha256'],'--action-plan',str(plan_path),'--action-plan-sha256',admission['plan_sha256'],
  '--action-cell-id',cell['cell_id'],'--action-output',str(output),'--action-mode','paid','--action-grant',str(directory/'grant.json'),
  '--action-grant-sha256',grant_pin,'--action-provider-source',str(provider),'--action-credential-reader-source',str(reader)]
 process=None
 try:
  with(directory/'stdout.log').open('xb')as out,(directory/'stderr.log').open('xb')as err:
   process=subprocess.Popen(command,cwd=outside,env=env,stdout=out,stderr=err,start_new_session=True)
   try:process.wait(timeout=300)
   except BaseException:
    terminate_cell_group(process);raise
  if process.returncode:terminate_cell_group(process)
  row['terminal_category']='parent_error'if process.returncode else'completed'
  p2=output/'propose-receipt.json';p3=output/'verify-receipt.json'
  if p2.is_file():
   row['consume']=json.loads(p2.read_bytes());consume=row['consume'];trace=consume.get('provider_trace')or{}
   row['emission_status']='confirmed_emitted'if consume['provider_called']and trace.get('http_status')is not None else'unknown'if consume['provider_called']else'confirmed_not_emitted'
   row['terminal_category']=consume['category']
   if consume['status']=='error'or trace.get('http_status')in(401,402,403,429):stop.set()
  else:row['emission_status']='unknown';stop.set()
  if p3.is_file():row['verification']=json.loads(p3.read_bytes());row['terminal_category']=row['verification']['category']
  if process.returncode:stop.set()
 except BaseException as error:
  if process is not None:terminate_cell_group(process)
  row.update(emission_status='unknown',terminal_category='supervision_error');stop.set()
  write_new(directory/'SUPERVISION-ERROR.json',{'type':type(error).__name__,'error':str(error)})
 write_new(directory/'ROW.json',row)
 with lock:
  finished[cell['cell_id']]=row
  progress={'completed_rows':len(finished),'planned_rows':len(selected),'full_plan_rows':576,'stop_requested':stop.is_set(),
   'elapsed_seconds':time.monotonic()-started,'observed_provider_called':sum(bool((r['consume']or{}).get('provider_called'))for r in finished.values())}
  temp=lab/'PROGRESS.tmp';temp.write_text(json.dumps(progress)+'\n');os.replace(temp,lab/'PROGRESS.json')
 return row
if experience:
 import types
 helpers=manifest['frozen_native_inputs'];item=helpers['fixture_contract.py']
 body=base64.b64decode(item['base64'],validate=True)
 assert sha(body)==item['sha256']and len(body)==item['bytes']
 contract=types.ModuleType('_independent_experience_contract')
 exec(compile(body,'fixture_contract.py','exec'),contract.__dict__)
 api=types.ModuleType('_qualified_experience_support');api.__file__=str(support)
 exec(compile(support.read_bytes(),str(support),'exec'),api.__dict__)
 fixture=json.loads(fixture_raw);worlds={w['world_id']:w for w in fixture['worlds']}
 assert fixture['schema']=='persistent-memory.experience-fixture.v1'and fixture['synthetic']is True and len(worlds)==12
 by_cell={c['cell_id']:c for c in selected};episode_results={}

 def empty_xp_row(cell,kind,episode_id,category='not_executed'):
  return {'cell':cell,'kind':kind,'episode_id':episode_id,'dataset_sha256':admission['dataset_sha256'],
   'plan_sha256':admission['plan_sha256'],'consume':None,'verification':None,
   'emission_status':'not_executed','terminal_category':category}

 def phase_process(cell,world,phase,directory,*,prior=None,prior_exit=None,extraction=None,extraction_exit=None,
                   a_verification=None,feedback=None,fake_body=None):
  folder=directory/phase;folder.mkdir(mode=0o700)
  projection=api.project_experience(world,cell,phase,dataset_sha256=admission['dataset_sha256'],plan_sha256=admission['plan_sha256'])
  projection_pin=write_new(folder/'input.json',projection)
  output=folder/'receipt.json'
  command=[str(python),'-I','-B',str(benchmark),'--action-transfer','--action-phase',phase,
   '--action-input',str(folder/'input.json'),'--action-input-sha256',projection_pin,'--action-output',str(output)]
  if phase in('observe','propose'):command+=['--action-state',str(directory/'state')]
  if phase in('propose','verify'):command+=['--action-artifacts',str(directory/'artifacts')]
  for label,value in(('prior-receipt',prior),('prior-exit',prior_exit),('extraction',extraction),
                     ('extraction-exit',extraction_exit),('verification',a_verification),('feedback',feedback)):
   if value is not None:
    path=folder/(label+'.json');pin=write_new(path,value)
    command+=['--action-'+label,str(path),'--action-'+label+'-sha256',pin]
  if phase in('propose','extract'):
   if stop.is_set()or time.time()>=admission['expires_at_epoch']or time.monotonic()-started>2100:
    raise InterruptedError('bounded_campaign_stopped_before_generation')
   if mode=='paid':
    grant_directory=directory.parent;grant_pin=make_grant(cell,grant_directory)
    command+=['--action-mode','paid','--action-grant',str(grant_directory/'grant.json'),
     '--action-grant-sha256',grant_pin,'--action-provider-source',str(provider),'--action-credential-reader-source',str(reader)]
   else:
    assert type(fake_body)is str
    fake={'schema':'persistent-memory.action-transfer.fake-response.v1','cell_id':cell['cell_id'],'body':fake_body,'finish_reason':'stop'}
    pin=write_new(folder/'fake.json',fake)
    command+=['--action-mode','fake','--action-fake-response',str(folder/'fake.json'),'--action-fake-response-sha256',pin]
   if phase=='extract':command+=['--action-ledger',str(directory.parent/'provider-budget.sqlite')]
  process=None
  with(folder/'stdout.log').open('xb')as out,(folder/'stderr.log').open('xb')as err:
   process=subprocess.Popen(command,cwd=outside,env=env,stdout=out,stderr=err,start_new_session=True)
   try:process.wait(timeout=300)
   except BaseException:terminate_cell_group(process);raise
  exited={'pid':process.pid,'returncode':process.returncode,'exited_ns':time.monotonic_ns()}
  write_new(folder/'EXIT.json',exited)
  if process.returncode:
   terminate_cell_group(process)
   message=(folder/'stderr.log').read_text()[-6000:]
   if any(code in message for code in ('complete_experience_input_exceeds_cap','complete_experience_context_exceeds_cap',
                                       'experience_prompt_context_cap','experience_context_cap','complete_request_byte_limit')):
    raise OverflowError('complete_raw_episode_exceeds_prespecified_cap')
   raise RuntimeError('experience_phase_failed:'+phase+':'+message)
  raw_receipt=output.read_bytes();receipt=json.loads(raw_receipt)
  assert(folder/'stdout.log').read_bytes()==raw_receipt and receipt['pid']==process.pid
  assert receipt['cell']==cell and receipt['dataset_sha256']==admission['dataset_sha256']and receipt['plan_sha256']==admission['plan_sha256']
  assert receipt['ended_ns']<=exited['exited_ns']
  return receipt,exited

 def fake_actions(cell,oracle):
  actions=[]
  for target,item in oracle['expected_files'].items():
   fmt=item['format']
   actions.append({'op':'emit_json','target':target,'value':fmt['value']}if fmt['kind']=='json'else
    {'op':'emit_csv','target':target,**{k:fmt[k]for k in('columns','rows','delimiter','encoding')}})
  actions.append({'op':'emit_json','target':'control.json','value':{'cell_id':cell['cell_id'],'completed':True}})
  return api.canonical({'schema':'artifact-actions-v1','actions':actions})

 def save_xp_row(cell,kind,episode_id,consume,verification,phases):
  row=empty_xp_row(cell,kind,episode_id);trace=consume.get('provider_trace')or{}
  row.update(consume=consume,verification=verification,phases=phases,
   emission_status='confirmed_not_emitted'if not consume.get('provider_called')else'confirmed_emitted'if trace.get('http_status')is not None else'unknown',
   terminal_category=consume['category']if verification is None else verification['category'])
  if trace.get('http_status')in(401,402,403,429)or consume['status']=='error':stop.set()
  write_new(cells/cell['cell_id']/'ROW.json',row)
  with lock:
   finished[cell['cell_id']]=row
   temp=lab/'PROGRESS.tmp';temp.write_text(json.dumps({'completed_rows':len(finished),'planned_rows':len(selected),
    'stop_requested':stop.is_set(),'elapsed_seconds':time.monotonic()-started})+'\n');os.replace(temp,lab/'PROGRESS.json')
  return row

 def xp_task(cell,case,mission,episode_id,extraction=None,extraction_exit=None):
  directory=cells/cell['cell_id'];directory.mkdir(mode=0o700);run=directory/'run';run.mkdir(mode=0o700)
  world=contract.project_case(case,mission)
  p1,e1=phase_process(cell,world,'observe',run,extraction=extraction,extraction_exit=extraction_exit)
  oracle=contract.get_oracle(case,mission)
  p2,e2=phase_process(cell,world,'propose',run,prior=p1,prior_exit=e1,
   fake_body=fake_actions(cell,oracle)if mode=='fake'else None)
  verified_world=dict(world,oracle=oracle)
  p3,e3=phase_process(cell,verified_world,'verify',run,prior=p2,prior_exit=e2)
  assert len({p1['pid'],p2['pid'],p3['pid']})==3
  phases={'observe':{'receipt':p1,'exit':e1},'propose':{'exit':e2},'verify':{'exit':e3}}
  return save_xp_row(cell,mission,episode_id,p2,p3,phases),e3

 def execute_episode(episode):
  episode_id=episode['episode_id'];case=worlds[episode['world_id']];rows={}
  all_ids=[episode['a_cell_id'],episode['extract_cell_id'],*episode['b_cell_ids'].values()]
  before=time.monotonic_ns();summary={'episode_id':episode_id,'started_ns':before,'status':'not_executed'}
  try:
   if stop.is_set()or time.time()>=admission['expires_at_epoch']or time.monotonic()-started>2100:return rows
   a_cell=by_cell[episode['a_cell_id']];a_row,a_exit=xp_task(a_cell,case,'A',episode_id);rows[a_cell['cell_id']]=a_row
   if stop.is_set():
    summary['status']='stopped_after_A';return rows
   actual={}
   for path in(cells/a_cell['cell_id']/'run/artifacts').iterdir():
    assert path.is_file()and not path.is_symlink()and path.stat().st_size<=16384
    actual[path.name]=path.read_bytes()
   feedback=contract.feedback_from_a(case,actual,episode_id+'-actual-feedback')
   summary['A_feedback']=feedback
   if not feedback['observed']['discriminating']or type(feedback['success'])is not bool:
    summary['status']='paired_B_unavailable_A_feedback'
    for cid in episode['b_cell_ids'].values():
     rows[cid]=empty_xp_row(by_cell[cid],'B',episode_id,'paired_A_feedback_unavailable')
    return rows
   xcell=by_cell[episode['extract_cell_id']];directory=cells/xcell['cell_id'];directory.mkdir(mode=0o700)
   run=directory/'run';run.mkdir(mode=0o700);world=contract.project_case(case,'A')
   literal=None
   if mode=='fake':
    try:source=api.experience_input(a_row['consume'],a_row['verification'],feedback)
    except ValueError as error:
     if str(error)=='complete_experience_input_exceeds_cap':raise OverflowError('complete_raw_episode_exceeds_prespecified_cap')from error
     raise
    trace_pin=sha(api.canonical(source['trace']).encode());feedback_pin=sha(api.canonical(source['feedback']).encode())
    literal=api.canonical({'schema':'experience-procedure-v1','convention_id':case['receiver_convention'],
     'scope':case['receiver_scope'],'evidence_refs':[trace_pin,feedback_pin],
     'text':contract.CONVENTIONS[case['family']][case['receiver_convention']]})
   extraction,extract_exit=phase_process(xcell,world,'extract',run,prior=a_row['consume'],prior_exit=a_exit,
    a_verification=a_row['verification'],feedback=feedback,fake_body=literal)
   rows[xcell['cell_id']]=save_xp_row(xcell,'extract',episode_id,extraction,None,{'extract':{'exit':extract_exit}})
   summary['lesson_grade']=contract.grade_lesson(case,extraction['procedure'],extraction['trace_sha256'],extraction['feedback_sha256'],feedback)
   # Full raw arm goes first: a cap failure censors all paired B conditions.
   for arm in('raw','derived','none','withdrawn'):
    if stop.is_set()or time.time()>=admission['expires_at_epoch']or time.monotonic()-started>2100:break
    bcell=by_cell[episode['b_cell_ids'][arm]]
    row,_=xp_task(bcell,case,'B',episode_id,extraction if arm!='none'else None,extract_exit if arm!='none'else None)
    rows[bcell['cell_id']]=row
   summary['status']='completed'if len(rows)==6 else'incomplete'
  except OverflowError as error:
   summary.update(status='paired_B_unavailable_raw_cap',error=str(error))
   for cid in episode['b_cell_ids'].values():
    rows[cid]=empty_xp_row(by_cell[cid],'B',episode_id,'paired_raw_cap_unavailable')
  except InterruptedError as error:
   summary.update(status='stopped_before_generation',error=str(error))
  except BaseException as error:
   stop.set();summary.update(status='supervision_error',error_type=type(error).__name__,error=str(error))
  finally:
   for cid in all_ids:
    rows.setdefault(cid,empty_xp_row(by_cell[cid],'extract'if cid==episode['extract_cell_id']else'A'if cid==episode['a_cell_id']else'B',episode_id))
   summary['ended_ns']=time.monotonic_ns();summary['elapsed_seconds']=(summary['ended_ns']-before)/1e9
   with lock:episode_results[episode_id]=summary
  return rows
rows={}
try:
 with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:
  futures={pool.submit(execute_episode,e):e for e in episodes}if experience else{pool.submit(execute,c):c for c in selected}
  for future in concurrent.futures.as_completed(futures):
   c=futures[future]
   if experience:
    rows.update(future.result());continue
   try:rows[c['cell_id']]=future.result()
   except BaseException as error:
    stop.set();rows[c['cell_id']]={'cell':c,'dataset_sha256':admission['dataset_sha256'],'plan_sha256':admission['plan_sha256'],
     'consume':None,'verification':None,'emission_status':'unknown','terminal_category':'worker_error'}
 for cell in plan['cells']:
  if cell['cell_id']not in selected_set:
   rows[cell['cell_id']]={'cell':cell,'dataset_sha256':admission['dataset_sha256'],'plan_sha256':admission['plan_sha256'],
    'consume':None,'verification':None,'emission_status':'not_executed','terminal_category':'not_selected_calibration'}
 observations={'schema':'persistent-memory.experience-observations.v1'if experience else'persistent-memory.action-transfer.observations.v1','dataset_sha256':admission['dataset_sha256'],
  'plan_sha256':admission['plan_sha256'],'mode':'paid','rows':[rows[c['cell_id']]for c in plan['cells']]}
 if experience:observations.update(mode=mode,episodes=[episode_results[e['episode_id']]for e in episodes],
   fake_proof_only=mode=='fake',descriptive_paired_results_only=True,runtime_activated=False)
 write_new(lab/'comparison.json',observations)
 import sqlite3
 reservations=[]
 for cell in selected:
  ledger=cells/cell['cell_id']/('provider-budget.sqlite'if experience and any(e['extract_cell_id']==cell['cell_id']for e in episodes)else'run/state/provider-budget.sqlite')
  if ledger.is_file():
   with sqlite3.connect('file:'+str(ledger)+'?mode=ro',uri=True)as connection:
    for cid,budget_sha,request_sha,amount in connection.execute('SELECT cell_id,budget_sha,request_sha,amount FROM reservations'):
     assert cid==cell['cell_id']and decimal.Decimal(amount)==units[cell['model']]
     reservations.append({'cell_id':cid,'budget_sha256':budget_sha,'request_sha256':request_sha,'reserved_USD':amount})
 assert len({x['cell_id']for x in reservations})==len(reservations)<=len(selected)
 selected_rows=[rows[c['cell_id']]for c in selected]
 result={'schema':'hermes.action-transfer.actual-execution.v1','candidate_sha256':_PIN_,'host':_HOST_,
   'passed':len(rows)==full_count and not stop.is_set()and(len(episode_results)==len(episodes)and all(e['status']in('completed','paired_B_unavailable_raw_cap','paired_B_unavailable_A_feedback')for e in episode_results.values())if experience else all(r['consume']is not None and r['verification']is not None and r['emission_status']!='not_executed'for r in selected_rows)),
   'purpose':admission['purpose'],'mode':mode,'planned_rows':len(selected),'full_plan_rows':full_count,'terminal_rows':len(selected_rows),'stop_requested':stop.is_set(),
  'provider_marked_called':sum(bool((r['consume']or{}).get('provider_called'))for r in rows.values()),
  'confirmed_emitted':sum(r['emission_status']=='confirmed_emitted'for r in rows.values()),
  'unknown_emission':sum(r['emission_status']=='unknown'for r in rows.values()),
  'verified_task_successes':sum((r['verification']or{}).get('task_success')is True for r in rows.values()),
  'reservations':reservations,'reserved_USD':str(sum((decimal.Decimal(x['reserved_USD'])for x in reservations),decimal.Decimal(0))),
  'comparison_sha256':sha((lab/'comparison.json').read_bytes()),'elapsed_seconds':time.monotonic()-started,
  'production_changed':False,'invoice_total_USD':None,'financial_admission_expires_at_epoch':admission['expires_at_epoch']}
 result['source_drift']={n:sha((repo/n).read_bytes())for n in expected}!={n:h['sha256']for n,h in expected.items()}
 if experience:
  result['fake_plumbing_readiness_passed']=(len(episode_results)==12
   and all(e['status']=='completed'for e in episode_results.values())
   and sum(r.get('kind')=='B'and(r['verification']or{}).get('task_success')is True
           and(r['verification']or{}).get('effect_verified')is True for r in selected_rows)==48
   and all((r['consume']or{}).get('procedure')is not None for r in selected_rows if r.get('kind')=='extract')
   and not reservations and result['provider_marked_called']==0)if mode=='fake'else None
 if result['source_drift']:result['passed']=False
 write_new(lab/'RESULT.json',result);print(json.dumps({k:v for k,v in result.items()if k!='reservations'}),flush=True)
except BaseException as error:
 if not(lab/'RESULT.json').exists():
  write_new(lab/'RESULT.json',{'schema':'hermes.action-transfer.actual-execution.v1','candidate_sha256':_PIN_,
   'host':_HOST_,'passed':False,'error_type':type(error).__name__,'error':str(error),
   'completed_rows':len(rows),'planned_rows':len(selected),'reserved_USD':None,
   'accounting_requires_ledger_reconciliation':True,'production_changed':False,'invoice_total_USD':None})
 traceback.print_exc();raise
