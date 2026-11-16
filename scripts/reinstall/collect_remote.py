"""Read-only collector. Its stdout contains secrets and must only be consumed in memory."""
import json
import hashlib
import subprocess
from pathlib import Path
import tomllib


def output(args):
    return subprocess.check_output(args, text=True, timeout=15).strip()


def collect():
    if output(['hostname']) != 'ubuntu-2625':
        raise RuntimeError('unexpected_host')
    iface = 'wlp4s0'
    uuid = output(['nmcli', '-g', 'GENERAL.CON-UUID', 'device', 'show', iface])
    def field(name, secrets=False):
        return output(['nmcli', *(['--show-secrets'] if secrets else []), '-g', name, 'connection', 'show', uuid])
    if field('connection.autoconnect') != 'yes' or field('connection.permissions'):
        raise RuntimeError('wifi_not_system_autoconnect')
    if field('802-11-wireless-security.key-mgmt') != 'wpa-psk':
        raise RuntimeError('unsupported_wifi_auth')
    if Path(f'/sys/class/net/{iface}/addr_assign_type').read_text().strip() != '0':
        raise RuntimeError('wifi_mac_not_permanent')
    original = tomllib.loads(Path('/etc/frp/frpc.toml').read_text())
    proxies = [p for p in original.get('proxies', []) if p.get('type') == 'tcp' and p.get('localPort') == 22]
    if len(proxies) != 1 or proxies[0].get('localIP', '127.0.0.1') not in ('127.0.0.1', 'localhost'):
        raise RuntimeError('ssh_proxy_not_unique_or_local')
    if original.get('auth', {}).get('method', 'token') != 'token' or not original.get('auth', {}).get('token'):
        raise RuntimeError('unsupported_frp_auth')
    frp = {k: original[k] for k in ['serverAddr', 'serverPort', 'auth', 'transport'] if k in original}
    frp['proxies'] = proxies
    frp['loginFailExit'] = False
    disk = json.loads(output(['sfdisk', '--json', '/dev/sda']))['partitiontable']
    frpc_path = output(['which', 'frpc'])
    return {
        'hostname': 'ubuntu-2625',
        'wifi': {'mac': Path(f'/sys/class/net/{iface}/address').read_text().strip(),
                 'ssid': field('802-11-wireless.ssid'),
                 'password': field('802-11-wireless-security.psk', True)},
        'disk': {'path': '/dev/sda', 'bytes': int(output(['blockdev', '--getsize64', '/dev/sda'])),
                 'gpt_id': disk['id'], 'serial': output(['lsblk', '-dn', '-o', 'SERIAL', '/dev/sda'])},
        'frp': frp,
        'frpc_path': frpc_path,
        'frpc_sha256': hashlib.sha256(Path(frpc_path).read_bytes()).hexdigest(),
        'frpc_version': output(['frpc', '--version']),
    }


if __name__ == '__main__':
    try:
        print(json.dumps(collect()))
    except Exception as e:
        print(json.dumps({'collection_error': type(e).__name__}))
        raise SystemExit(1)
