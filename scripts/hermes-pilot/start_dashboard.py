"""Start the official dashboard with an administrator UID and loopback host port."""
import json,os,subprocess
from pathlib import Path

ROOT=Path('/srv/hermes-pilot')
ETC=Path('/etc/hermes-pilot')
NAME='hermes-dashboard'

def main():
    if os.geteuid()!=0:raise RuntimeError('root required')
    credentials=ETC/'credentials.env'
    if credentials.stat().st_mode&0o077:raise RuntimeError('private env permissions required')
    values=dict(line.split('=',1) for line in credentials.read_text().splitlines() if '=' in line)
    if not values.get('HERMES_DASHBOARD_OAUTH_CLIENT_ID','').startswith('agent:'):
        raise RuntimeError('registered OAuth client required')
    if values.get('HERMES_DASHBOARD_PUBLIC_URL')!='https://sm.briconbric.com':
        raise RuntimeError('expected public URL required')
    if subprocess.run(['docker','inspect',NAME],capture_output=True).returncode==0:
        raise RuntimeError('dashboard exists; inspect it before replacement')
    config=ROOT/'policy/config.yaml'
    if config.stat().st_uid!=10001:raise RuntimeError('administrator must own config')
    image=json.loads((ROOT/'screen-image.json').read_text())['image_id']
    args=['docker','run','-d','--name',NAME,'--label','org.springmonkey.pilot=hermes-dashboard',
          '--restart','unless-stopped','--init','--user','10001:10000','--cap-drop','ALL',
          '--security-opt','no-new-privileges:true','--cpus','1.5','--memory','3g',
          '--memory-swap','3g','--pids-limit','512','--shm-size','512m','--publish','127.0.0.1:9119:8080',
          '--env-file',str(credentials),'--env','HOME=/opt/data',
          '--env','XDG_RUNTIME_DIR=/tmp/hermes-admin-runtime',
          '--env','HERMES_WRITE_SAFE_ROOT=/workspace',
          '--mount','type=bind,src='+str(ROOT/'data')+',dst=/opt/data',
          '--mount','type=bind,src='+str(ROOT/'policy')+',dst=/opt/policy',
          '--mount','type=bind,src='+str(ROOT/'data/skill-bundles')+',dst=/opt/data/skill-bundles,readonly',
          '--mount','type=bind,src='+str(ROOT/'workspace')+',dst=/workspace',
          '--mount','type=bind,src='+str(ROOT/'approved-skills')+',dst=/opt/data/skills,readonly',
          '--mount','type=bind,src='+str(ETC/'AGENTS.md')+',dst=/workspace/AGENTS.md,readonly',
          '--log-opt','max-size=10m','--log-opt','max-file=3','--entrypoint','/bin/sh',image,
          '-c','set -eu; umask 007; mkdir -p "$XDG_RUNTIME_DIR"; /opt/hermes/.venv/bin/hermes webapp --skip-build --no-open >/dev/null; /usr/sbin/nginx -e /dev/stderr -c /opt/pilot/webapp-ingress.conf; exec /opt/hermes/.venv/bin/hermes dashboard --host 0.0.0.0 --port 9119 --skip-build --no-open']
    subprocess.run(args,check=True,capture_output=True)
    print(json.dumps({'dashboard_started':True,'host_bind':'127.0.0.1:9119',
                      'uid':10001,'agent_uid':10000,'public_url':values['HERMES_DASHBOARD_PUBLIC_URL'],
                      'image_id':image,'oauth_client_configured':True}))

if __name__=='__main__':main()
