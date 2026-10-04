import argparse
import json
from pathlib import Path
from .core import Authority,Memory,MemoryError
from .interfaces import dispatch,make_server,mcp_stdio

def demo(directory):
    p=Path(directory);p.mkdir(parents=True,exist_ok=True)
    a=Authority.create(p/'retained'/'authority.db',p/'retained-anchor'/'checkpoint.json')
    m=Memory.create(p/'memory.db',a)
    A=m.register_source('demo','A','A: crimson secret flower',alias='a.md')['ref']
    B=m.register_source('demo','B','B: blue public river',alias='b.md')['ref']
    F=m.derive('demo','F','crimson flower fact','fact',[{'ref':A,'relation':'derives'}],m.checkpoint()['epoch'])['ref']
    W=m.compile_deterministic('demo','W',[F])['ref']
    V=m.derive('demo','V','crimson indexed fragment','vector',[{'ref':W,'relation':'indexes'}],m.checkpoint()['epoch'])['ref']
    m.drain_outbox();m.backup(p/'before-revocation.db')
    before=m.search('demo','crimson');plan=m.plan_revocation('demo','A')
    m.revoke_source('demo','A','demo-revoke-A');m.drain_outbox()
    old=Memory.open(p/'before-revocation.db',a)
    quarantine=old.read(B);restore=old.restore_verify(a.checkpoint())
    after=[old.read(r) for r in [A,F,W,V]]
    kept=old.read(B)
    assert before and all(not x['allowed'] for x in after) and kept['allowed'] and not quarantine['allowed']
    return {'before_count':len(before),'revocation_plan':plan,'quarantine':quarantine,'restore':restore,'after':after,'B':kept,'physical_erasure':False}

def main(argv=None):
    p=argparse.ArgumentParser(prog='hermes-memory')
    p.add_argument('--authority');p.add_argument('--anchor');p.add_argument('--store')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('init')
    rp=sub.add_parser('rpc');rp.add_argument('request')
    sp=sub.add_parser('serve');sp.add_argument('--host',default='127.0.0.1');sp.add_argument('--port',default=8079,type=int);sp.add_argument('--token-file')
    sub.add_parser('mcp')
    dp=sub.add_parser('demo');dp.add_argument('--directory',required=True)
    args=p.parse_args(argv)
    if args.command=='demo':result=demo(args.directory)
    else:
        if not all([args.authority,args.anchor,args.store]):p.error('--authority, --anchor and --store are required')
        if args.command=='init':
            a=Authority.create(args.authority,args.anchor);m=Memory.create(args.store,a);result={'initialized':True,'checkpoint':a.checkpoint()}
        else:
            a=Authority.open(args.authority,args.anchor);m=Memory.open(args.store,a)
            if args.command=='rpc':result=dispatch(m,json.loads(args.request))
            elif args.command=='mcp':return mcp_stdio(m)
            else:
                token=Path(args.token_file).read_text(encoding='utf-8').strip() if args.token_file else None
                server=make_server(m,args.host,args.port,token)
                try:server.serve_forever()
                finally:server.server_close()
                return
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
