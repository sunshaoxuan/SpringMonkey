import asyncio
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timezone
import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from budget_gate import (BUDGET, Blocked, ENDPOINTS, Ledger, actual_cost, charge,
                         create_app, prepare_body, validate_policy)

TOKEN = 'fixture-gate-token-' + 'x'*32

@pytest.fixture
def policy():
    return {'pilot_id':'fixture','budget_micro_usd':BUDGET,'routes':{
        name:{'base_url':url,'model':name+'-fixture','key_env':'FIXTURE_ONLY',
          'price_confirmed':True,'price_source':'fixture only, no supplier attestation',
          'valid_until':'2099-01-01T00:00:00Z','max_input_tokens':1_000_000,
          'max_output_tokens':1000,'input_micro_usd_per_million':1_000_000,
          'output_micro_usd_per_million':2_000_000} for name,url in ENDPOINTS.items()}}

@pytest.fixture
def ledger(tmp_path,policy):
    return Ledger.initialize(tmp_path/'budget.sqlite',policy)

def payload(model='gpt-fixture',**kw):
    return {'model':model,'messages':[{'role':'user','content':'fixture'}],**kw}

def client(policy,ledger,fn):
    return TestClient(create_app(policy,ledger,TOKEN,{n:'fixture-upstream-'+n for n in ENDPOINTS},httpx.MockTransport(fn)))

def post(c,body=None,path='/gpt/v1/chat/completions'):
    return c.post(path,json=body or payload(),headers={'Authorization':'Bearer '+TOKEN})

def test_total_budget_is_ten_dollars_and_never_reinitialized(ledger,policy):
    assert ledger.state()['budget_micro_usd']==10_000_000
    first=ledger.reserve('gpt',6_000_000); ledger.settle(first,6_000_000)
    reopened=Ledger(ledger.path,policy)
    assert reopened.state()['committed_and_reserved_micro_usd']==6_000_000
    final=reopened.reserve('qwen',4_000_000);reopened.settle(final,4_000_000)
    with pytest.raises(Blocked,match='exhausted'): reopened.reserve('deepseek',1)
    assert Ledger(ledger.path,policy).state()['halted']=='budget_exhausted'
    with pytest.raises(FileExistsError):Ledger.initialize(ledger.path,policy)

def test_concurrent_admission_is_atomic(ledger,policy):
    def reserve(_):
        try:return Ledger(ledger.path,policy).reserve('gpt',6_000_000)
        except Blocked:return None
    with ThreadPoolExecutor(max_workers=6) as pool: results=list(pool.map(reserve,range(12)))
    assert sum(x is not None for x in results)==1
    assert ledger.state()['committed_and_reserved_micro_usd']==6_000_000

def test_pending_crash_blocks_restart_and_missing_database_fails_closed(ledger,policy,tmp_path):
    ledger.reserve('gpt',1_000_000)
    with pytest.raises(Blocked,match='review'):Ledger(ledger.path,policy).assert_startable()
    with pytest.raises(Blocked,match='missing'):Ledger(tmp_path/'absent',policy).state()
    assert not (tmp_path/'absent').exists()

def test_corruption_and_policy_change_fail_closed(ledger,policy,tmp_path):
    changed=copy.deepcopy(policy);changed['pilot_id']='other'
    with pytest.raises(Blocked,match='identity'):Ledger(ledger.path,changed).state()
    bad=tmp_path/'bad.sqlite';bad.write_bytes(b'broken')
    with pytest.raises(Blocked,match='unavailable'):Ledger(bad,policy).state()

@pytest.mark.parametrize('value',[None,0,-1,False,1.5,float('nan')])
def test_unknown_or_invalid_price_rejected(policy,value):
    policy['routes']['gpt']['input_micro_usd_per_million']=value
    with pytest.raises(Blocked):validate_policy(policy)

def test_unconfirmed_expired_price_and_raised_budget_rejected(policy):
    for key,value in [('price_confirmed',False),('valid_until','2000-01-01T00:00:00Z')]:
        p=copy.deepcopy(policy);p['routes']['qwen'][key]=value
        with pytest.raises(Blocked):validate_policy(p)
    policy['budget_micro_usd']=20_000_000
    with pytest.raises(Blocked):validate_policy(policy)

def test_unknown_usage_is_charged_full_ceiling(ledger):
    call=ledger.reserve('gpt',1_000_000);ledger.settle(call)
    assert ledger.state()['committed_and_reserved_micro_usd']==1_000_000
    with sqlite3.connect(ledger.path) as db:
        assert db.execute('SELECT uncertain FROM calls').fetchone()==(1,)
    with pytest.raises(Blocked):ledger.settle(call,0)

def test_retries_auxiliary_and_three_routes_share_one_ledger(policy,ledger):
    seen=[]
    def upstream(request):
        seen.append((request.url.host,json.loads(request.content)))
        return httpx.Response(200,json={'choices':[],'usage':{'prompt_tokens':100,'completion_tokens':20}})
    with client(policy,ledger,upstream) as c:
        for route in ['gpt','deepseek','qwen','gpt','deepseek']:
            assert post(c,payload(route+'-fixture'),'/'+route+'/v1/chat/completions').status_code==200
    assert len(seen)==5
    assert ledger.state()['committed_and_reserved_micro_usd']==700
    assert all(body['max_tokens']==1000 and body['n']==1 for _,body in seen)

def test_budget_stop_precedes_any_upstream_request(policy,ledger):
    first=ledger.reserve('gpt',9_500_000);ledger.settle(first,9_500_000)
    seen=[]
    with client(policy,ledger,lambda r:seen.append(r)) as c:
        assert post(c).status_code==402
        assert post(c,payload('deepseek-fixture'),'/deepseek/v1/chat/completions').status_code==402
    assert seen==[]

@pytest.mark.parametrize('status',[429,500,503])
def test_availability_errors_keep_ceiling_and_allow_next_route(policy,ledger,status):
    seen=[]
    def upstream(request):
        seen.append(request.url.host)
        return httpx.Response(status if len(seen)==1 else 200,json={'usage':{'prompt_tokens':1,'completion_tokens':1}})
    with client(policy,ledger,upstream) as c:
        assert post(c).status_code==status
        assert post(c,payload('deepseek-fixture'),'/deepseek/v1/chat/completions').status_code==200
    assert len(seen)==2
    assert ledger.state()['committed_and_reserved_micro_usd']==1_002_003

def test_timeout_is_not_free_and_no_automatic_http_retry(policy,ledger):
    calls=[]
    def fail(request):
        calls.append(request);raise httpx.ReadTimeout('fixture only')
    with client(policy,ledger,fail) as c: assert post(c).status_code==502
    assert len(calls)==1
    assert ledger.state()['committed_and_reserved_micro_usd']==1_002_000

def test_cancellation_before_response_keeps_cost_and_closes_request(policy,ledger):
    async def upstream(request):raise asyncio.CancelledError()
    app=create_app(policy,ledger,TOKEN,{n:'fixture-upstream-'+n for n in ENDPOINTS},httpx.MockTransport(upstream))
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as c:
            with pytest.raises(asyncio.CancelledError):
                await c.post('/gpt/v1/chat/completions',json=payload(),headers={'Authorization':'Bearer '+TOKEN})
    asyncio.run(scenario())
    assert ledger.state()['pending']==0
    assert ledger.state()['committed_and_reserved_micro_usd']==1_002_000

@pytest.mark.parametrize('body',[payload(n=2),payload(max_tokens=1001),payload(max_tokens=1,max_completion_tokens=1),
    payload(service_tier='priority'),payload(tools=[{'type':'web_search'}]),
    payload(messages=[{'role':'user','content':[{'type':'image_url','image_url':{'url':'fixture'}}]}]),
    payload(messages=[{'role':'user','content':'text','audio':{}}]),payload(stream='true'),payload(model='other')])
def test_unpriced_paths_are_rejected_before_charge(policy,ledger,body):
    with client(policy,ledger,lambda r:pytest.fail('upstream must not be called')) as c:
        assert post(c,body).status_code==400
        assert c.post('/gpt/v1/responses',json={}).status_code==404
    assert ledger.state()['committed_and_reserved_micro_usd']==0

def test_auth_models_redirect_and_headers(policy,ledger):
    def upstream(request):
        assert request.headers['authorization']=='Bearer fixture-upstream-gpt'
        return httpx.Response(302,headers={'location':'https://unapproved.invalid','set-cookie':'secret'},content=b'')
    with client(policy,ledger,upstream) as c:
        assert c.get('/gpt/v1/models').status_code==401
        assert c.get('/gpt/v1/models',headers={'Authorization':'Bearer '+TOKEN}).json()['data'][0]['id']=='gpt-fixture'
        assert c.post('/gpt/v1/chat/completions',json=payload()).status_code==401
        r=post(c);assert r.status_code==302 and 'location' not in r.headers and 'set-cookie' not in r.headers

class Chunks(httpx.AsyncByteStream):
    def __init__(self,parts,fail=False):self.parts,self.fail=parts,fail
    async def __aiter__(self):
        for part in self.parts:yield part
        if self.fail:raise httpx.ReadError('fixture interrupted stream')

@pytest.mark.parametrize('complete',[True,False])
def test_stream_usage_and_disconnect_conservative_settlement(policy,ledger,complete):
    parts=[b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n',
           b'data: {"choices":[],"usage":{"prompt_tokens":100,"completion_tokens":20}}\n\n']
    if complete:parts.append(b'data: [DONE]\n\n')
    def upstream(request):
        assert json.loads(request.content)['stream_options']=={'include_usage':True}
        return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Chunks(parts))
    with client(policy,ledger,upstream) as c:
        r=post(c,payload(stream=True));assert r.content==b''.join(parts)
    assert ledger.state()['committed_and_reserved_micro_usd']==(140 if complete else 1_002_000)

def test_real_stream_transport_error_charges_reservation(policy,ledger):
    def upstream(request):return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Chunks([b'data: {}\n\n'],True))
    with client(policy,ledger,upstream) as c:
        with pytest.raises(Exception):post(c,payload(stream=True))
    assert ledger.state()['committed_and_reserved_micro_usd']==1_002_000

def test_invalid_usage_cannot_refund_or_hide_price_breach(policy,ledger):
    def upstream(request):return httpx.Response(200,json={'usage':{'prompt_tokens':1_000_001,'completion_tokens':1}})
    with client(policy,ledger,upstream) as c:
        assert post(c).status_code==502
    assert ledger.state()['pending']==1
    with pytest.raises(Blocked):Ledger(ledger.path,policy).assert_startable()

def test_missing_usage_receipt_keeps_full_reservation(policy,ledger):
    with client(policy,ledger,lambda r:httpx.Response(200,json={'choices':[]})) as c:assert post(c).status_code==200
    assert ledger.state()['committed_and_reserved_micro_usd']==1_002_000

def test_broker_refuses_agent_upstream_key_reuse(policy,ledger):
    with pytest.raises(Blocked):create_app(policy,ledger,TOKEN,{n:TOKEN for n in ENDPOINTS})

def test_example_remains_fail_closed_without_gateway_prices():
    from pathlib import Path
    example=json.loads((Path(__file__).parents[1]/'pilot-budget.example.json').read_text())
    with pytest.raises(Blocked,match='unverified_price_gpt'):validate_policy(example)
