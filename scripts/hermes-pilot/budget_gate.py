"""Private text-only inference gate with one persistent USD10 pilot budget.

Upstream pricing/context/output ceilings are trusted operator attestations. This
module cannot enforce a supplier's bill when those attestations are incorrect.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import uuid

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

BUDGET = 10_000_000  # integer micro-USD; cumulative for the entire pilot
MAX_BODY = 65_536
MAX_RESPONSE = 8_388_608
ENDPOINTS = {
    'gpt': 'https://ccnode.briconbric.com:49530/v1',
    'deepseek': 'https://api.deepseek.com',
    'qwen': 'https://ccnode.briconbric.com:49530/v1',
}

class Blocked(Exception):
    def __init__(self, code: str, status: int = 503):
        self.code, self.status = code, status
        super().__init__(code)

def integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise Blocked('invalid_integer', 400)
    return value

def charge(prompt, completion, route):
    return (prompt * route['input_micro_usd_per_million'] +
            completion * route['output_micro_usd_per_million'] + 999_999) // 1_000_000

def validate_policy(policy, now=None):
    now = now or datetime.now(timezone.utc)
    if policy.get('budget_micro_usd') != BUDGET or not policy.get('pilot_id') or set(policy.get('routes', {})) != set(ENDPOINTS):
        raise Blocked('invalid_policy')
    for name, route in policy['routes'].items():
        if route.get('base_url') != ENDPOINTS[name] or not route.get('model') or not route.get('key_env'):
            raise Blocked('invalid_route_' + name)
        if route.get('price_confirmed') is not True or not route.get('price_source'):
            raise Blocked('unverified_price_' + name)
        try:
            expiry = datetime.fromisoformat(route['valid_until'].replace('Z', '+00:00'))
            if expiry.tzinfo is None or expiry <= now:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise Blocked('stale_price_' + name) from None
        for key in ['max_input_tokens', 'max_output_tokens', 'input_micro_usd_per_million', 'output_micro_usd_per_million']:
            integer(route.get(key), 1)
        if charge(route['max_input_tokens'], route['max_output_tokens'], route) > BUDGET:
            raise Blocked('request_ceiling_exceeds_total_' + name)

def policy_hash(policy):
    return hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

class Ledger:
    def __init__(self, path: Path, policy: dict):
        self.path, self.policy = Path(path), policy
        self.identity = policy_hash(policy)

    @classmethod
    def initialize(cls, path, policy):
        validate_policy(policy)
        path = Path(path)
        # Explicit one-time initialization only. Normal startup never creates a DB.
        with path.open('xb'):
            pass
        with sqlite3.connect(path) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE meta (identity TEXT NOT NULL, budget INTEGER NOT NULL CHECK(budget=10000000), halted TEXT)')
            db.execute('CREATE TABLE calls (id TEXT PRIMARY KEY, route TEXT NOT NULL, reserved INTEGER NOT NULL CHECK(reserved>0), charged INTEGER, uncertain INTEGER NOT NULL DEFAULT 0, CHECK(charged IS NULL OR (charged>=0 AND charged<=reserved)))')
            db.execute('INSERT INTO meta VALUES (?,?,NULL)', (policy_hash(policy), BUDGET))
        return cls(path, policy)

    @contextmanager
    def transaction(self):
        db = None
        try:
            if not self.path.is_file() or self.path.is_symlink():
                raise Blocked('ledger_missing')
            db = sqlite3.connect(self.path.resolve().as_uri() + '?mode=rw', uri=True, timeout=5, isolation_level=None)
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT identity,budget,halted FROM meta').fetchall()
            if len(rows) != 1 or rows[0][0] != self.identity or rows[0][1] != BUDGET:
                raise Blocked('ledger_identity_mismatch')
            yield db, rows[0][2]
            db.commit()
        except sqlite3.Error:
            if db: db.rollback()
            raise Blocked('ledger_unavailable') from None
        finally:
            if db: db.close()

    def state(self):
        with self.transaction() as (db, halted):
            used, pending = db.execute('SELECT COALESCE(SUM(COALESCE(charged,reserved)),0),SUM(charged IS NULL) FROM calls').fetchone()
            return {'budget_micro_usd': BUDGET, 'committed_and_reserved_micro_usd': used,
                    'pending': pending or 0, 'halted': halted}

    def assert_startable(self):
        s = self.state()
        if s['pending'] or s['halted']:
            raise Blocked('pilot_requires_review')

    def reserve(self, route, amount):
        integer(amount, 1)
        with self.transaction() as (db, halted):
            if halted:
                raise Blocked('pilot_stopped', 402)
            used, pending = db.execute('SELECT COALESCE(SUM(COALESCE(charged,reserved)),0),SUM(charged IS NULL) FROM calls').fetchone()
            if pending:
                raise Blocked('inflight_limit', 429)
            if used + amount > BUDGET:
                db.execute("UPDATE meta SET halted='budget_exhausted'")
                db.commit()
                raise Blocked('pilot_budget_exhausted', 402)
            call_id = str(uuid.uuid4())
            db.execute('INSERT INTO calls(id,route,reserved) VALUES(?,?,?)', (call_id, route, amount))
            return call_id

    def settle(self, call_id, actual=None):
        with self.transaction() as (db, halted):
            row = db.execute('SELECT reserved,charged FROM calls WHERE id=?', (call_id,)).fetchone()
            if row is None or row[1] is not None:
                raise Blocked('invalid_settlement')
            if actual is not None and (type(actual) is not int or actual < 0 or actual > row[0]):
                db.execute("UPDATE meta SET halted='price_contract_violation'")
                db.commit()
                raise Blocked('price_contract_violation')
            db.execute('UPDATE calls SET charged=?,uncertain=? WHERE id=?',
                       (row[0] if actual is None else actual, int(actual is None), call_id))

ALLOWED = {'model','messages','tools','tool_choice','temperature','top_p','max_tokens','max_completion_tokens',
           'stream','stream_options','response_format','reasoning_effort','thinking','parallel_tool_calls',
           'seed','stop','frequency_penalty','presence_penalty','verbosity','n'}

def prepare_body(body, route):
    if not isinstance(body, dict) or set(body) - ALLOWED or body.get('model') != route['model']:
        raise Blocked('unsupported_request', 400)
    if body.get('n', 1) != 1 or type(body.get('n', 1)) is not int:
        raise Blocked('multiple_candidates_disabled', 400)
    if 'max_tokens' in body and 'max_completion_tokens' in body:
        raise Blocked('ambiguous_output_limit', 400)
    field = 'max_completion_tokens' if 'max_completion_tokens' in body else 'max_tokens'
    limit = integer(body.get(field, route['max_output_tokens']), 1)
    if limit > route['max_output_tokens']:
        raise Blocked('output_limit_exceeded', 400)
    if type(body.get('stream', False)) is not bool:
        raise Blocked('invalid_stream', 400)
    messages = body.get('messages')
    if not isinstance(messages, list) or not messages:
        raise Blocked('missing_messages', 400)
    for message in messages:
        if not isinstance(message, dict): raise Blocked('invalid_message', 400)
        if set(message)-{'role','content','name','tool_calls','tool_call_id','reasoning_content'}:
            raise Blocked('unsupported_message_fields', 400)
        content = message.get('content')
        if content is not None and not isinstance(content, str):
            if not isinstance(content, list) or any(not isinstance(x, dict) or set(x)-{'type','text'} or x.get('type')!='text' or not isinstance(x.get('text'),str) for x in content):
                raise Blocked('paid_multimodal_disabled', 400)
    if not isinstance(body.get('tools', []), list) or any(not isinstance(t, dict) or set(t)-{'type','function'} or t.get('type')!='function' for t in body.get('tools', [])):
        raise Blocked('provider_tools_disabled', 400)
    body = dict(body)
    body[field], body['n'] = limit, 1
    if body.get('stream'):
        body['stream_options'] = {'include_usage': True}
    else:
        body.pop('stream_options', None)
    # Full supplier input-context ceiling covers message, tool and template tokens.
    return body, charge(route['max_input_tokens'], limit, route), limit

def actual_cost(usage, route, limit):
    if not isinstance(usage, dict): return None
    prompt, completion = usage.get('prompt_tokens'), usage.get('completion_tokens')
    if type(prompt) is not int or type(completion) is not int or prompt < 0 or completion < 0:
        return None
    if prompt > route['max_input_tokens'] or completion > limit:
        raise Blocked('price_contract_violation')
    return charge(prompt, completion, route)

def create_app(policy, ledger, token, credentials, transport=None):
    validate_policy(policy)
    ledger.assert_startable()
    if len(token) < 32 or token in credentials.values() or any(not credentials.get(name) for name in ENDPOINTS):
        raise Blocked('missing_credentials')
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(Blocked)
    async def blocked_handler(request, exc):
        return JSONResponse({'error': {'type': 'pilot_guard', 'code': exc.code}}, status_code=exc.status)

    @app.get('/{name}/v1/models')
    async def models(name: str, request: Request):
        if not hmac.compare_digest(request.headers.get('authorization',''), 'Bearer '+token):
            raise Blocked('unauthorized', 401)
        if name not in ENDPOINTS or request.url.query: raise Blocked('unknown_route', 404)
        validate_policy(policy)
        return {'object':'list','data':[{'id':policy['routes'][name]['model'],'object':'model'}]}

    @app.post('/{name}/v1/chat/completions')
    async def completion(name: str, request: Request):
        if not hmac.compare_digest(request.headers.get('authorization',''), 'Bearer '+token):
            raise Blocked('unauthorized', 401)
        validate_policy(policy)  # Recheck price expiry on every request.
        if name not in ENDPOINTS or request.url.query:
            raise Blocked('unknown_route', 404)
        if request.headers.get('content-encoding') or request.headers.get('content-type','').split(';')[0] != 'application/json':
            raise Blocked('unsupported_content_type', 400)
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BODY: raise Blocked('request_too_large', 413)
            chunks.append(chunk)
        try: body = json.loads(b''.join(chunks))
        except (ValueError, UnicodeError): raise Blocked('invalid_json', 400) from None
        route = policy['routes'][name]
        body, reserved, limit = prepare_body(body, route)
        call_id = ledger.reserve(name, reserved)
        client = httpx.AsyncClient(transport=transport or httpx.AsyncHTTPTransport(retries=0), timeout=60,
                                   follow_redirects=False, trust_env=False)
        response = None
        try:
            req = client.build_request('POST', route['base_url']+'/chat/completions', json=body,
                       headers={'Authorization': 'Bearer '+credentials[name], 'Content-Type':'application/json'})
            response = await client.send(req, stream=True)
        except BaseException as exc:
            try:
                ledger.settle(call_id)  # May have reached the supplier; retain the full ceiling.
            finally:
                await asyncio.shield(client.aclose())
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            raise Blocked('upstream_transport_failed', 502) from None

        if body.get('stream') and response.status_code == 200 and 'text/event-stream' in response.headers.get('content-type',''):
            async def stream():
                receipt, done, buffer, size = None, False, b'', 0
                try:
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_RESPONSE: raise Blocked('response_too_large')
                        buffer += chunk
                        if len(buffer) > MAX_BODY: raise Blocked('stream_frame_too_large')
                        while b'\n' in buffer:
                            line, buffer = buffer.split(b'\n',1)
                            if line.startswith(b'data:'):
                                payload = line[5:].strip()
                                if payload == b'[DONE]': done = True
                                else:
                                    try: event = json.loads(payload)
                                    except ValueError: continue
                                    if isinstance(event,dict) and event.get('usage') is not None:
                                        receipt = event['usage']
                        yield chunk
                finally:
                    try:
                        ledger.settle(call_id, actual_cost(receipt, route, limit) if done else None)
                    finally:
                        await asyncio.shield(response.aclose())
                        await asyncio.shield(client.aclose())
            return StreamingResponse(stream(), media_type='text/event-stream')
        data = bytearray()
        try:
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_RESPONSE: raise Blocked('response_too_large')
            receipt = None
            if response.status_code == 200:
                try:
                    decoded = json.loads(data)
                    receipt = decoded.get('usage') if isinstance(decoded,dict) else None
                except ValueError: pass
            ledger.settle(call_id, actual_cost(receipt, route, limit))
            # Forward body/status only; never forward upstream authentication or cookies.
            return Response(bytes(data), status_code=response.status_code,
                            media_type='application/json')
        except Exception:
            # Preserve reservation on any parsing/settlement failure. Restart stays blocked.
            raise Blocked('unsettled_upstream', 502) from None
        finally:
            await response.aclose()
            await client.aclose()
    return app

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['validate','init','status','serve'])
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--ledger', type=Path)
    args = parser.parse_args()
    try:
        policy = json.loads(args.policy.read_text(encoding='utf-8'))
        validate_policy(policy)
        if args.action == 'validate':
            print(json.dumps({'ready': True, 'budget_micro_usd': BUDGET}))
            return 0
        if args.ledger is None: raise Blocked('ledger_required')
        ledger = Ledger.initialize(args.ledger, policy) if args.action == 'init' else Ledger(args.ledger,policy)
        if args.action in {'init','status'}:
            print(json.dumps(ledger.state()))
            return 0
        import uvicorn
        app = create_app(policy,ledger,os.environ.get('HERMES_PILOT_GATE_TOKEN',''),
                         {n:os.environ.get(r['key_env'],'') for n,r in policy['routes'].items()})
        uvicorn.run(app,host='127.0.0.1',port=41000,access_log=False)
        return 0
    except (Blocked, OSError, ValueError) as exc:
        print(json.dumps({'ready': False,'code':exc.code if isinstance(exc,Blocked) else type(exc).__name__}))
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
