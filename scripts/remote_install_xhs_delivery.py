#!/usr/bin/env python3
"""Run the pulled repository installer; send recipient privately on SSH stdin."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from openclaw_ssh_password import load_openclaw_ssh_password

REMOTE_CODE = r'''
import json,os,subprocess,sys
from pathlib import Path
value=json.load(sys.stdin).get('recipient','')
if value:
    import re,grp
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value):
        raise ValueError('invalid recipient')
    path=Path('/etc/openclaw/openclaw.env')
    path.parent.mkdir(parents=True,exist_ok=True)
    lines=path.read_text().splitlines() if path.exists() else []
    lines=[l for l in lines if not l.startswith('OPENCLAW_OWNER_GOOGLE_EMAIL=')]
    path.write_text('\n'.join(lines+[f'OPENCLAW_OWNER_GOOGLE_EMAIL={value}'])+'\n')
    path.chmod(0o640)
    os.chown(path,0,grp.getgrnam('openclaw').gr_gid)
subprocess.run(['python3','/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw/install_xhs_delivery.py'],check=True)
'''


def main() -> int:
    import paramiko
    import shlex
    client=paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(os.environ.get('OPENCLAW_SSH_HOST','ccnode.briconbric.com'),
                   port=int(os.environ.get('OPENCLAW_SSH_PORT','8822')), username='root',
                   password=load_openclaw_ssh_password(), allow_agent=False,look_for_keys=False)
    try:
        stdin,out,err=client.exec_command('python3 -c '+shlex.quote(REMOTE_CODE),timeout=900)
        stdin.write(json.dumps({'recipient':os.environ.get('OPENCLAW_OWNER_GOOGLE_EMAIL','')}))
        stdin.channel.shutdown_write()
        sys.stdout.buffer.write(out.read())
        sys.stderr.buffer.write(err.read())
        return out.channel.recv_exit_status()
    finally:
        client.close()


if __name__=='__main__':
    raise SystemExit(main())
