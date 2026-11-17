"""Install only the dedicated Hermes certificate renewal lifecycle."""
from pathlib import Path
import json
import os
import subprocess

SOURCE = Path('/srv/hermes-dashboard-public')
FILES = [
    ('dashboard-cert-deploy.sh', '/etc/letsencrypt/renewal-hooks/deploy/90-hermes-dashboard-nginx', 0o755),
    ('hermes-dashboard-cert-renew.service', '/etc/systemd/system/hermes-dashboard-cert-renew.service', 0o644),
    ('hermes-dashboard-cert-renew.timer', '/etc/systemd/system/hermes-dashboard-cert-renew.timer', 0o644),
]


def main():
    if os.geteuid() != 0:
        raise RuntimeError('root required')
    if not Path('/etc/letsencrypt/renewal/sm.briconbric.com.conf').is_file():
        raise RuntimeError('dedicated certificate must already exist')
    # Check all destinations before changing any file.
    for name, target, _ in FILES:
        dest = Path(target)
        if dest.exists() and dest.read_bytes() != (SOURCE / name).read_bytes():
            raise RuntimeError('review existing owned renewal file before overwriting')
    for name, target, mode in FILES:
        dest = Path(target)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((SOURCE / name).read_bytes())
        dest.chmod(mode)
    subprocess.run(['sh', '-n', FILES[0][1]], check=True)
    subprocess.run(['systemd-analyze', 'verify', FILES[1][1], FILES[2][1]], check=True)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'hermes-dashboard-cert-renew.timer'], check=True)
    print(json.dumps({'dedicated_renewal_installed': True}))


if __name__ == '__main__':
    main()
