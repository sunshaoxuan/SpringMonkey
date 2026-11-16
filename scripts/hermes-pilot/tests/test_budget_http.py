"""A real local HTTP supplier fixture, with no external calls or real credentials."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import httpx
from fastapi.testclient import TestClient

from budget_gate import BUDGET, ENDPOINTS, Ledger, create_app

def test_real_http_forwarding_and_stop_survive_new_ledger_object(tmp_path):
    observed=[]
    class Supplier(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['content-length'])))
            observed.append((self.path,self.headers['authorization'],body))
            data=json.dumps({'choices':[{'message':{'role':'assistant','content':'fixture ok'},'finish_reason':'stop'}],
                             'usage':{'prompt_tokens':100,'completion_tokens':20}}).encode()
            self.send_response(200);self.send_header('content-type','application/json')
            self.send_header('content-length',str(len(data)));self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',0),Supplier)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    class LocalOnly(httpx.AsyncBaseTransport):
        def __init__(self):self.inner=httpx.AsyncHTTPTransport(retries=0)
        async def handle_async_request(self,request):
            target=request.url.copy_with(scheme='http',host='127.0.0.1',port=server.server_port)
            request=httpx.Request(request.method,target,headers=request.headers,content=await request.aread())
            return await self.inner.handle_async_request(request)
        async def aclose(self):await self.inner.aclose()
    policy={'pilot_id':'http-fixture','budget_micro_usd':BUDGET,'routes':{
      n:{'base_url':u,'model':n+'-fixture','key_env':'FIXTURE_ONLY','price_confirmed':True,
         'price_source':'synthetic fixture','valid_until':'2099-01-01T00:00:00Z',
         'max_input_tokens':1_000_000,'max_output_tokens':1000,
         'input_micro_usd_per_million':1_000_000,'output_micro_usd_per_million':2_000_000}
      for n,u in ENDPOINTS.items()}}
    token='fixture-local-agent-token-'+'x'*32
    ledger=Ledger.initialize(tmp_path/'budget.sqlite',policy)
    try:
        app=create_app(policy,ledger,token,{n:'fixture-upstream-'+n for n in ENDPOINTS},LocalOnly())
        with TestClient(app) as client:
            body={'model':'gpt-fixture','messages':[{'role':'user','content':'fixture'}]}
            headers={'Authorization':'Bearer '+token}
            response=client.post('/gpt/v1/chat/completions',json=body,headers=headers)
            assert response.status_code==200 and response.json()['choices'][0]['message']['content']=='fixture ok'
            assert observed[0][0]=='/v1/chat/completions'
            assert observed[0][1]=='Bearer fixture-upstream-gpt'
            assert observed[0][2]['max_tokens']==1000
            assert token not in json.dumps(observed)
            used=ledger.state()['committed_and_reserved_micro_usd']
            call=ledger.reserve('fixture-cost',9_500_000-used);ledger.settle(call,9_500_000-used)
            assert client.post('/gpt/v1/chat/completions',json=body,headers=headers).status_code==402
            assert len(observed)==1
        restored=Ledger(ledger.path,policy).state()
        assert restored['committed_and_reserved_micro_usd']==9_500_000 and restored['halted']=='budget_exhausted'
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
