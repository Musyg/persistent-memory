"""Actual-provider CLI; refuses an absent, unapproved or differently hashed budget."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import platform
import stat

from bounded_provider import Budget, BoundedProviderClient

INPUT_SHA='271dcdd1d7025a15d41f9c4e766d8cfc1dad7625c2ce0db489e3be7cede9c037'


def read_credential(path, *, env_file=False, field='DEEPSEEK_API_KEY'):
    # Open once without following the final symlink, then validate the same inode
    # that is read. The shared production env may be owner/group readable (0640).
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
    with os.fdopen(fd,'r',encoding='utf-8') as stream:
        info=os.fstat(stream.fileno())
        mode=stat.S_IMODE(info.st_mode)
        permitted=mode==0o600 or (env_file and mode==0o640 and info.st_gid==os.getegid())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or not permitted:
            raise ValueError('private_credential_file_required')
        if env_file:
            if field not in ('DEEPSEEK_API_KEY','OPENAI_API_KEY'):
                raise ValueError('credential_field_not_allowed')
            values=[]
            for line in stream:
                line=line.strip()
                if line.startswith(field+'='):
                    values.append(line.split('=',1)[1].strip().strip('\"\''))
            if len(values)!=1:raise ValueError('credential_field_missing_or_ambiguous')
            key=values[0]
        else:
            key=stream.read(4097).strip()
    if not key or len(key)>4096:raise ValueError('credential_invalid')
    return key


def load_inputs(path, *, expected_sha256=INPUT_SHA, public_portable=False):
    raw=path.read_bytes()
    if type(expected_sha256) is not str or len(expected_sha256)!=64 or hashlib.sha256(raw).hexdigest()!=expected_sha256:raise ValueError('inputs_not_frozen')
    value=json.loads(raw)
    if value.get('schema')!=('persistent-memory.public-replay.inputs.v1' if public_portable else 'hermes.g2c.inputs.v1') or value.get('synthetic') is not True:
        raise ValueError('input_schema')
    if value.get('budget')!={'top_k':5,'max_context_chars':2000,'candidate_limit':100}:
        raise ValueError('retrieval_budget_changed')
    return value['cases']


def main():
    p=argparse.ArgumentParser()
    for name in ('inputs','output','budget'):
        p.add_argument('--'+name,type=Path,required=True)
    for name in ('source','tokenizer','profile'):
        p.add_argument('--'+name,type=Path)
    p.add_argument('--consumer',choices=('historical','public_portable'),default='historical')
    p.add_argument('--dataset-sha256')
    secrets=p.add_mutually_exclusive_group(required=True)
    secrets.add_argument('--api-key-file',type=Path)
    secrets.add_argument('--credential-env-file',type=Path)
    p.add_argument('--budget-sha256',required=True)
    args=p.parse_args()
    if platform.system()!='Linux':raise ValueError('linux_only')
    if args.output.exists():raise ValueError('new_output_directory_required')
    portable=args.consumer=='public_portable'
    if portable:
        if args.profile is None or args.dataset_sha256 is None:raise ValueError('public_profile_and_dataset_pin_required')
        from portable_consumer import run_cells, load_inputs as load_public_inputs
        profile=json.loads(args.profile.read_bytes())
        dataset_sha=args.dataset_sha256
        cases=load_public_inputs(args.inputs,expected_sha256=dataset_sha)
        # The OpenAI profiles prove tokens by complete UTF8 bytes plus framing,
        # not by a private tokenizer or an unverified alias-specific encoding.
        from bounded_provider import json_bytes
        tokenizer=lambda messages:len(json_bytes(messages))+1024
    else:
        if args.source is None or args.tokenizer is None:raise ValueError('historical_source_and_tokenizer_required')
        from consumer_runner import run_cells
        from official_tokenizer import OfficialTokenizer
        profile=None
        dataset_sha=INPUT_SHA
        cases=load_inputs(args.inputs)
        tokenizer=OfficialTokenizer(args.tokenizer)
    # Budget validation occurs before credential reading and before network transport creation.
    budget_ledger=args.output.with_name(args.output.name+'-budget.sqlite')
    budget=Budget(args.budget,args.budget_sha256,budget_ledger,tokenizer=tokenizer,
                  **({'max_requests':profile['max_requests'],'dataset_sha256':dataset_sha,
                      'prospective_profile':profile} if portable else {}))
    api_key=read_credential(args.api_key_file or args.credential_env_file,
                           env_file=args.credential_env_file is not None,
                           field='OPENAI_API_KEY' if portable else 'DEEPSEEK_API_KEY')
    def provider(cell_id):
        return BoundedProviderClient(budget,api_key)
    report=asyncio.run(run_cells(args.source,cases,args.output,provider,
        mode='public_portable' if portable else 'consumer_utility',dataset_sha256=dataset_sha,
        **({'cells':profile['cells']} if portable else {})))
    print(json.dumps({'attempts':len(report['attempts']),'completed':sum(r['status']=='completed' for r in report['attempts']),
        'report':str(args.output/'report.json'),'promoted':False}))


if __name__=='__main__':main()
