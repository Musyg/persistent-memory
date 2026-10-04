"""Bounded local RPC and MCP stdio interfaces; no third-party dependencies."""
import hmac
import ipaddress
import json
from pathlib import Path
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .core import MemoryError, require

OPERATIONS=frozenset({'register_source','derive','read','validate','resolve','resolve_many','aliases','rename','bind_alias','checkpoint','revoke_source','get_revocation','explain_artifact','plan_revocation','set_status','search','context','project','projection_search','reconcile','drain_outbox','restore_verify','compile_deterministic'})

def dispatch(memory,request):
    require(type(request) is dict,'invalid_request')
    request=dict(request);op=request.pop('op',None)
    require(type(op) is str and op in OPERATIONS,'unknown_operation')
    return getattr(memory,op)(**request)

def make_server(memory,host='127.0.0.1',port=8079,token=None):
    loopback=host=='localhost'
    try:loopback=loopback or ipaddress.ip_address(host).is_loopback
    except ValueError:pass
    require(loopback or type(token) is str and len(token)>=32,'network_token_required')
    if token is not None:require(type(token) is str and len(token)>=32,'invalid_token')
    class Handler(BaseHTTPRequestHandler):
        server_version='HermesMemory/0.1'
        def setup(self):
            super().setup();self.connection.settimeout(5)
        def log_message(self,*args):
            pass
        def answer(self,status,value):
            raw=json.dumps(value,ensure_ascii=False).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
        def authorized(self):
            return token is None or hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token)
        def do_GET(self):
            if not self.authorized():return self.answer(401,{'error':'unauthorized'})
            if self.path!='/health':return self.answer(404,{'error':'not_found'})
            try:return self.answer(200,{'status':'ok','checkpoint':memory.checkpoint()})
            except (OSError,ValueError,sqlite3.Error):return self.answer(503,{'error':'authority_unavailable'})
        def do_POST(self):
            if not self.authorized():return self.answer(401,{'error':'unauthorized'})
            if self.path not in {'/rpc','/validate'}:return self.answer(404,{'error':'not_found'})
            try:
                require(self.headers.get('Transfer-Encoding') is None,'transfer_encoding_unsupported')
                length=int(self.headers.get('Content-Length','-1'))
                require(0<length<=1048576,'invalid_body_size')
                raw=self.rfile.read(length);require(len(raw)==length,'truncated_body')
                request=json.loads(raw)
                if self.path=='/validate':
                    require(type(request) is dict and set(request)=={'refs'},'invalid_validate_request')
                    request={'op':'validate',**request}
                return self.answer(200,dispatch(memory,request))
            except (MemoryError,TypeError,ValueError):return self.answer(400,{'error':'invalid_or_ineligible_request'})
            except (OSError,sqlite3.Error):return self.answer(503,{'error':'authority_or_store_unavailable'})
    return ThreadingHTTPServer((host,port),Handler)

REF_SCHEMA={'type':'object','properties':{k:{'type':'string','minLength':1} for k in ('workspace','artifact_id','version_id')},'required':['workspace','artifact_id','version_id'],'additionalProperties':False}
TOOLS=[
 {'name':'memory_read','description':'Read an exact memory version through current validity authority.','inputSchema':{'type':'object','properties':{'ref':REF_SCHEMA},'required':['ref'],'additionalProperties':False}},
 {'name':'memory_search','description':'Lexical search of eligible current versions in one workspace.','inputSchema':{'type':'object','properties':{'workspace':{'type':'string'},'query':{'type':'string'},'limit':{'type':'integer','minimum':1,'maximum':100}},'required':['workspace','query'],'additionalProperties':False}},
 {'name':'memory_explain','description':'Explain metadata dependencies without returning private content.','inputSchema':{'type':'object','properties':{'ref':REF_SCHEMA},'required':['ref'],'additionalProperties':False}}
]
class MCPSession:
    protocol='2025-03-26'
    def __init__(self,memory):self.memory=memory;self.initialized=False;self.ready=False
    def handle(self,msg):
        ident=msg.get('id') if type(msg) is dict else None
        def error(code,message):return {'jsonrpc':'2.0','id':ident,'error':{'code':code,'message':message}}
        if type(msg) is not dict or msg.get('jsonrpc')!='2.0' or type(msg.get('method')) is not str:return error(-32600,'Invalid Request')
        method=msg['method'];params=msg.get('params',{})
        if type(params) is not dict:return error(-32602,'Invalid params')
        if 'id' not in msg:
            if method=='notifications/initialized' and self.initialized:self.ready=True
            return None
        if method=='ping':result={}
        elif method=='initialize':
            if self.initialized:return error(-32600,'Already initialized')
            if type(params.get('protocolVersion')) is not str or type(params.get('capabilities')) is not dict or type(params.get('clientInfo')) is not dict:return error(-32602,'Invalid initialize params')
            self.initialized=True
            result={'protocolVersion':self.protocol,'capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'hermes-memory-core','version':'0.1.0'}}
        elif not self.ready:return error(-32002,'Initialization required')
        elif method=='tools/list':result={'tools':TOOLS}
        elif method=='tools/call':
            mapping={'memory_read':'read','memory_search':'search','memory_explain':'explain_artifact'}
            tool=params.get('name');args=params.get('arguments',{})
            if tool not in mapping or type(args) is not dict or 'op' in args:return error(-32602,'Unknown tool or invalid arguments')
            try:
                value=dispatch(self.memory,{'op':mapping[tool],**args})
                result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}],'isError':False}
            except (MemoryError,TypeError,ValueError,OSError,sqlite3.Error):
                result={'content':[{'type':'text','text':'Request invalid, ineligible, or authority unavailable'}],'isError':True}
        else:return error(-32601,'Method not found')
        return {'jsonrpc':'2.0','id':ident,'result':result}

def mcp_stdio(memory,stdin=None,stdout=None):
    stdin=stdin or sys.stdin;stdout=stdout or sys.stdout;session=MCPSession(memory)
    while True:
        line=stdin.readline(1048577)
        if not line:return
        if len(line)>1048576:raise MemoryError('mcp_message_limit')
        try:response=session.handle(json.loads(line))
        except json.JSONDecodeError:response={'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Parse error'}}
        if response is not None:stdout.write(json.dumps(response,ensure_ascii=False)+'\n');stdout.flush()
