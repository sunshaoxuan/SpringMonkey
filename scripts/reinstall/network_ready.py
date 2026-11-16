"""First-boot connectivity gate; run in the new system, never on the old host."""
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import time


def command(argv):
    return subprocess.check_output(argv, text=True, timeout=15).strip()


def main():
    cfg = json.loads(Path('/etc/reset-connectivity.json').read_text())
    deadline = time.monotonic() + 150
    iface = None
    while time.monotonic() < deadline:
        for p in Path('/sys/class/net').iterdir():
            if (p / 'address').read_text().strip().lower() != cfg['network_mac'].lower():
                continue
            state = command(['nmcli', '-g', 'GENERAL.STATE', 'device', 'show', p.name])
            route = json.loads(command(['ip', '-j', 'route', 'show', 'default']))
            addresses = json.loads(command(['ip', '-j', '-4', 'address', 'show', 'dev', p.name]))
            if state.startswith('100') and any(r.get('dev') == p.name for r in route) and any(
                    a.get('scope') == 'global' for d in addresses for a in d.get('addr_info', [])):
                if cfg['mode'] == 'production' and not (p / 'wireless').exists():
                    raise ValueError('wifi_interface_required')
                iface = p.name
                break
        if iface: break
        time.sleep(2)
    if not iface: raise TimeoutError('network_not_ready')
    user = pwd.getpwnam('springadmin')
    home = Path(user.pw_dir)
    for p, mode in [(home / '.ssh', 0o700), (home / '.ssh/authorized_keys', 0o600)]:
        if p.stat().st_uid != user.pw_uid or stat.S_IMODE(p.stat().st_mode) != mode:
            raise ValueError('ssh_user_permissions_invalid')
    if Path('/etc/reset-admin.pub').read_text().strip() not in (home / '.ssh/authorized_keys').read_text().splitlines():
        raise ValueError('ssh_authorized_key_missing')
    subprocess.run(['/usr/sbin/sshd', '-t'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for args in [['default', 'deny', 'incoming'], ['default', 'allow', 'outgoing'],
                 ['allow', 'in', 'on', iface, 'to', 'any', 'port', '22', 'proto', 'tcp'],
                 ['allow', 'in', 'on', 'tailscale0', 'to', 'any', 'port', '22', 'proto', 'tcp'],
                 ['--force', 'enable']]:
        subprocess.run(['ufw', *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    Path('/run/reset-connectivity-ready').write_text('network, ssh key and firewall ready\n')


if __name__ == '__main__':
    try: main()
    except Exception as e:
        print('connectivity_gate_FAIL_' + type(e).__name__)
        raise SystemExit(1)
