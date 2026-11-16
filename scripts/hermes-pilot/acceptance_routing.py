"""Exercise installed Hermes with synthetic loopback providers, without live secrets."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,threading
from run_agent import AIAgent

counts={}
requests=[]
mode='availability'
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
        if self.path.endswith('/api/show'):
            self.send_response(404);self.send_header('Content-Length','2');self.end_headers();self.wfile.write(b'{}');return
        requests.append({'path':self.path,'fields':list(body),'stream':body.get('stream')})
        route=self.path.split('/')[1];counts[route]=counts.get(route,0)+1
        body.setdefault('model',route)
        status=200
        if mode=='availability' and route in ['primary','secondary']:
            status=503;result={'error':{'message':'Synthetic temporary outage','type':'server_error','code':'server_error'}}
        elif mode=='refusal':
            result={'id':'synthetic','object':'chat.completion','model':body['model'],'choices':[{'index':0,'message':{'role':'assistant','content':'Synthetic provider refusal','refusal':'Synthetic provider refusal'},'finish_reason':'content_filter'}],'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}
        else:
            result={'id':'synthetic','object':'chat.completion','model':body['model'],'choices':[{'index':0,'message':{'role':'assistant','content':'HERMES_ROUTING_OK'},'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}
        streaming=body.get('stream') and status==200
        if streaming:
            choice=result['choices'][0]
            chunk={'id':'synthetic','object':'chat.completion.chunk','created':1,'model':body['model'],'choices':[{'index':0,'delta':choice['message'],'finish_reason':choice['finish_reason']}]}
            data=('data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n').encode()
        else:data=json.dumps(result).encode()
        self.send_response(status);self.send_header('Content-Type','text/event-stream' if streaming else 'application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
base='http://127.0.0.1:'+str(server.server_port)
reports=[]
try:
    for mode in ['availability','refusal']:
        counts.clear();requests.clear()
        fallback=[{'provider':'custom','model':name,'base_url':base+'/'+name+'/v1','api_key':'synthetic-local-key','api_mode':'chat_completions'} for name in ['secondary','tertiary']]
        agent=AIAgent(model='primary',provider='custom',base_url=base+'/primary/v1',api_key='synthetic-local-key',api_mode='chat_completions',fallback_model=fallback,max_iterations=6,enabled_toolsets=[],quiet_mode=True,skip_context_files=True,skip_memory=True,skip_background_review=True,load_soul_identity=False,save_trajectories=False,reasoning_config={'enabled':False},run_budget_seconds=90)
        result=agent.run_conversation('Return the routing test marker.')
        text=str(result.get('final_response',''))
        ok=(counts.get('tertiary',0)>0 and 'HERMES_ROUTING_OK' in text) if mode=='availability' else (counts.get('primary',0)==1 and not counts.get('secondary') and not counts.get('tertiary') and 'refusal' in text.lower())
        reports.append({'case':mode,'passed':ok,'request_counts':dict(counts),'requests':list(requests),'final_model':agent.model,'final_response':text[:300]})
finally:server.shutdown()
print(json.dumps({'synthetic_providers':True,'installed_agent':True,'cases':reports}))
if not all(x['passed'] for x in reports):raise SystemExit(1)
