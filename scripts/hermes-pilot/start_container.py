"""Start the authorized CLI pilot from an already built immutable local image."""
import json
import os
from pathlib import Path
import subprocess

ROOT=Path('/srv/hermes-pilot')
ETC=Path('/etc/hermes-pilot')
NAME='hermes-pilot'

def main():
    if os.geteuid()!=0:raise RuntimeError('root required for Docker administration')
    credentials=ETC/'credentials.env'
    if credentials.stat().st_uid!=0 or credentials.stat().st_mode & 0o077:
        raise RuntimeError('credential file permissions')
    image=json.loads((ROOT/'custom-image.json').read_text())['image_id']
    prior=subprocess.run(['docker','inspect',NAME],capture_output=True)
    if prior.returncode==0:raise RuntimeError('container already exists; inspect before changing it')
    data=ROOT/'cli-home';data.mkdir(mode=0o700,exist_ok=True)
    os.chown(data,10000,10000);data.chmod(0o700)
    config=ROOT/'policy/config.yaml'
    if not config.exists() or config.stat().st_uid!=10001:
        raise RuntimeError('administrator-owned canonical config required')
    workspace=ROOT/'workspace';workspace.mkdir(mode=0o750,exist_ok=True)
    os.chown(workspace,10000,10000)
    args=['docker','run','-d','--name',NAME,'--hostname','springmonkey-hermes',
          '--label','org.springmonkey.pilot=hermes','--restart','unless-stopped',
          '--cpus','1.5','--memory','3g','--memory-swap','3g','--pids-limit','512',
          '--security-opt','no-new-privileges:true','--user','10000:10000',
          '--entrypoint','sleep','--env-file',str(credentials),
          '--env','HERMES_WRITE_SAFE_ROOT=/workspace:/opt/data',
          '--env','HERMES_MANAGED_DIR=/opt/policy',
          '--mount','type=bind,src='+str(data)+',dst=/opt/data',
          '--mount','type=bind,src='+str(ROOT/'policy')+',dst=/opt/policy,readonly',
          '--mount','type=bind,src='+str(ROOT/'data/skill-bundles')+',dst=/opt/data/skill-bundles,readonly',
          '--mount','type=bind,src='+str(ROOT/'workspace')+',dst=/workspace',
          '--mount','type=bind,src='+str(ROOT/'approved-skills')+',dst=/opt/data/skills,readonly',
          '--mount','type=bind,src='+str(ETC/'AGENTS.md')+',dst=/workspace/AGENTS.md,readonly',
          '--log-opt','max-size=10m','--log-opt','max-file=3',image,'infinity']
    subprocess.run(args,check=True,capture_output=True)
    wrapper=Path('/usr/local/bin/hermes-pilot')
    wrapper.write_text('#!/bin/sh\nset -eu\nexec /usr/bin/flock -n /run/lock/hermes-pilot.lock '
        '/usr/bin/docker exec -i --user 10000:10000 --workdir /workspace hermes-pilot '
        '/usr/bin/timeout --signal=TERM 900 /opt/hermes/.venv/bin/hermes "$@"\n')
    wrapper.chmod(0o755)
    obj=json.loads(subprocess.check_output(['docker','inspect',NAME]))[0]
    host=obj['HostConfig']
    report={'name':NAME,'image_id':obj['Image'],'running':obj['State']['Running'],
            'memory':host['Memory'],'memory_swap':host['MemorySwap'],'nano_cpus':host['NanoCpus'],
            'pids_limit':host['PidsLimit'],'restart_policy':host['RestartPolicy']['Name'],
            'port_bindings':host.get('PortBindings'),'security_opt':host['SecurityOpt'],
            'mounts':[{'destination':m['Destination'],'rw':m['RW']} for m in obj['Mounts']]}
    (ROOT/'container-started.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
