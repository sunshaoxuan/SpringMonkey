"""Official Ubuntu Docker repository installer for the explicitly authorized pilot.

Run on the target host as root; does not change Wi-Fi, SSH, Tailscale or FRP config.
"""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import urllib.request

ROOT=Path('/srv/hermes-pilot')
FINGERPRINT='D3306A018370199E527AE7997EA0A9C3F273FCD8'

def run(args,**kwargs):
    return subprocess.run(args,check=True,capture_output=True,**kwargs)

def main():
    release=platform.freedesktop_os_release()
    if os.geteuid()!=0 or release.get('ID')!='ubuntu' or release.get('VERSION_ID')!='26.10':
        raise RuntimeError('unexpected host environment')
    ROOT.mkdir(mode=0o700,exist_ok=True)
    if not shutil.which('docker'):
        baseline={}
        for name,args in [('iptables',['iptables-save']),('ip6tables',['ip6tables-save']),('ufw',['ufw','status','verbose'])]:
            baseline[name]=run(args,text=True).stdout
        (ROOT/'network-before-docker.json').write_text(json.dumps(baseline,indent=2)+'\n')
        os.chmod(ROOT/'network-before-docker.json',0o600)
        key=urllib.request.urlopen('https://download.docker.com/linux/ubuntu/gpg',timeout=30).read(100000)
        with tempfile.TemporaryDirectory(prefix='hermes-docker-key-',dir='/run') as home:
            metadata=run(['gpg','--batch','--homedir',home,'--with-colons','--show-keys'],input=key).stdout.decode()
        if FINGERPRINT not in metadata:raise RuntimeError('Docker signing key mismatch')
        key_path=Path('/etc/apt/keyrings/docker.asc')
        key_path.parent.mkdir(mode=0o755,exist_ok=True);key_path.write_bytes(key);key_path.chmod(0o644)
        architecture=run(['dpkg','--print-architecture'],text=True).stdout.strip()
        if architecture!='amd64':raise RuntimeError('unexpected architecture')
        Path('/etc/apt/sources.list.d/docker.sources').write_text(
            'Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: stonking\n'
            'Components: stable\nArchitectures: amd64\nSigned-By: /etc/apt/keyrings/docker.asc\n')
        env={**os.environ,'DEBIAN_FRONTEND':'noninteractive','NEEDRESTART_MODE':'l'}
        with (ROOT/'docker-install.log').open('wb') as log:
            os.chmod(ROOT/'docker-install.log',0o600)
            for args in [['apt-get','update'],['apt-get','install','-y','docker-ce','docker-ce-cli','containerd.io','docker-buildx-plugin']]:
                subprocess.run(args,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
    versions=run(['dpkg-query','-W','-f=${Package} ${Version}\n','docker-ce','docker-ce-cli','containerd.io','docker-buildx-plugin'],text=True).stdout
    services={s:run(['systemctl','is-active',s],text=True).stdout.strip() for s in ['docker','ssh','tailscaled','frpc']}
    report={'packages':versions.splitlines(),'services':services,'published_ports':False,'signing_key_fingerprint':FINGERPRINT}
    (ROOT/'docker-installed.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
