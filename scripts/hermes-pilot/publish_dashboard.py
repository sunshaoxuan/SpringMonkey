"""Prepare or activate only the dedicated sm.briconbric.com Nginx site."""
from pathlib import Path
import argparse,json,os,shutil,subprocess

SITE=Path('/etc/nginx/sites-available/hermes-sm.conf')
LINK=Path('/etc/nginx/sites-enabled/hermes-sm.conf')
SOURCE=Path('/srv/hermes-dashboard-public')

def prepare():
    if os.geteuid()!=0:raise RuntimeError('root required')
    SOURCE.mkdir(mode=0o700,exist_ok=True)
    for tool in ['iptables','ip6tables','nginx','certbot']:
        if not shutil.which(tool):raise RuntimeError('missing required tool '+tool)
    for name,dest,mode in [('dashboard-firewall.sh','/usr/local/sbin/hermes-dashboard-firewall',0o755),
                            ('hermes-dashboard-firewall.service','/etc/systemd/system/hermes-dashboard-firewall.service',0o644)]:
        p=Path(dest)
        if p.exists() and p.read_bytes()!=(SOURCE/name).read_bytes():
            raise RuntimeError('review existing owned service before overwriting')
        p.write_bytes((SOURCE/name).read_bytes());p.chmod(mode)
    subprocess.run(['systemctl','daemon-reload'],check=True,capture_output=True)
    subprocess.run(['systemctl','enable','--now','hermes-dashboard-firewall.service'],check=True,capture_output=True)
    if SITE.exists() or LINK.exists():raise RuntimeError('site already exists; inspect it')
    Path('/var/www/hermes-acme').mkdir(mode=0o755,exist_ok=True)
    SITE.write_text('''server {
    listen 80;
    listen [::]:80;
    server_name sm.briconbric.com;
    location ^~ /.well-known/acme-challenge/ { root /var/www/hermes-acme; }
    location / { return 503 "Hermes dashboard is being configured.\\n"; }
}
''')
    LINK.symlink_to(SITE)
    check=subprocess.run(['nginx','-t'],capture_output=True,text=True)
    if check.returncode:
        LINK.unlink();raise RuntimeError('dedicated Nginx site validation failed')
    subprocess.run(['systemctl','reload','nginx'],check=True,capture_output=True)
    print(json.dumps({'public_site_prepared':True,'dashboard_http_exposed':False,
                      'acme_webroot_ready':True,'frp_port_loopback_only':True}))

def activate():
    assert SITE.exists() and LINK.resolve()==SITE
    cert=Path('/etc/letsencrypt/live/sm.briconbric.com/fullchain.pem')
    if not cert.exists():
        p=subprocess.run(['certbot','certonly','--webroot','-w','/var/www/hermes-acme',
                          '--cert-name','sm.briconbric.com','-d','sm.briconbric.com',
                          '--non-interactive'],capture_output=True,text=True,timeout=180)
        (SOURCE/'certbot-result.log').write_text(p.stdout+p.stderr)
        if p.returncode:raise RuntimeError('certificate issuance failed; inspect protected certificate log')
    backup=SOURCE/'nginx-before-activation.conf';backup.write_bytes(SITE.read_bytes())
    SITE.write_bytes((SOURCE/'dashboard-nginx.conf').read_bytes())
    if subprocess.run(['nginx','-t'],capture_output=True).returncode:
        SITE.write_bytes(backup.read_bytes());raise RuntimeError('TLS site validation failed; restored HTTP site')
    subprocess.run(['systemctl','reload','nginx'],check=True,capture_output=True)
    print(json.dumps({'https_site_active':True,'domain':'sm.briconbric.com','certificate_present':True}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','activate'])
    globals()[parser.parse_args().action]()
