"""Build unarmed Windows-DPAPI recovery material or a secret-free VM fixture."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import secrets
import sys
import zipfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import yaml

HERE = Path(__file__).resolve().parent
SERVICE = '''[Unit]
Description=SSH recovery tunnel
Wants=network-online.target
After=network-online.target ssh.service
Requires=reset-connectivity-ready.service
After=reset-connectivity-ready.service
[Service]
User=frp
ExecStart=/usr/local/bin/frpc -c /etc/frp/frpc.toml
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
UMask=0077
[Install]
WantedBy=multi-user.target
'''


def keypair():
    key = Ed25519PrivateKey.generate()
    return (key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                              serialization.NoEncryption()),
            key.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH) + b'\n')


def frp_config(config):
    if set(config) - {'serverAddr', 'serverPort', 'auth', 'transport', 'proxies', 'loginFailExit'}:
        raise ValueError('unsupported_frp_global')
    if len(config.get('proxies', [])) != 1:
        raise ValueError('exactly_one_ssh_proxy_required')
    p = config['proxies'][0]
    if set(p) - {'name', 'type', 'localIP', 'localPort', 'remotePort'}:
        raise ValueError('unsupported_proxy_options')
    if p.get('type') != 'tcp' or p.get('localPort') != 22 or p.get('localIP', '127.0.0.1') not in ('127.0.0.1', 'localhost'):
        raise ValueError('non_ssh_proxy_rejected')
    if config['auth'].get('method', 'token') != 'token' or not config['auth'].get('token'):
        raise ValueError('missing_frp_token')
    lines = []
    def emit(table, value):
        if table: lines.append('[' + table + ']')
        for k, v in value.items():
            if not isinstance(v, dict): lines.append(k + ' = ' + json.dumps(v, ensure_ascii=True))
        for k, v in value.items():
            if isinstance(v, dict): emit(table + '.' + k if table else k, v)
    emit('', {k: v for k, v in config.items() if k != 'proxies'})
    lines.append('[[proxies]]')
    lines.extend(k + ' = ' + json.dumps(v, ensure_ascii=True) for k, v in p.items())
    return ('\n'.join(lines) + '\n').encode()


def make_files(data, debs, fixture=False, keys=None):
    if not data['wifi']['ssid'] or not 8 <= len(data['wifi']['password']) <= 64:
        raise ValueError('invalid_wifi_credentials')
    if keys is None:
        admin_private, admin_public = keypair()
        host_private, host_public = keypair()
    else:
        admin_private, admin_public, host_private, host_public = keys
    network = {'version': 2, 'renderer': 'NetworkManager', 'wifis': {'resetwifi': {
        'match': {'macaddress': data['wifi']['mac']}, 'dhcp4': True, 'dhcp6': True,
        'access-points': {data['wifi']['ssid']: {'password': data['wifi']['password']}}}}}
    if fixture:
        network['wifis']['resetwifi']['optional'] = True
        network['ethernets'] = {'testnic': {'match': {'macaddress': '52:54:00:aa:00:01'}, 'dhcp4': True}}
    files = {
        'payload/network.yaml': yaml.safe_dump({'network': network}, sort_keys=False).encode(),
        'payload/frpc.toml': frp_config(data['frp']),
        'payload/frpc.service': SERVICE.encode(),
        'payload/admin.pub': admin_public,
        'payload/ssh_host_ed25519_key': host_private,
        'payload/ssh_host_ed25519_key.pub': host_public,
    }
    for name in ['guard.py', 'install_target.py', 'bootstrap.sh', 'network_ready.py', 'reset-connectivity-ready.service', 'tailscaled-recovery.service', 'initramfs-release.sh', 'persist_failure.py']:
        files['payload/' + name] = (HERE / name).read_bytes()
    for name, content in debs.items():
        if Path(name).name != name or not name.endswith('.deb'):
            raise ValueError('invalid_deb_name')
        files['payload/debs/' + name] = content
    if not debs:
        raise ValueError('offline_dependencies_required')
    connectivity = {'mode': 'fixture' if fixture else 'production',
                    'network_mac': '52:54:00:aa:00:01' if fixture else data['wifi']['mac'],
                    'frp_server': data['frp']['serverAddr'], 'frp_port': data['frp']['serverPort']}
    files['payload/connectivity.json'] = json.dumps(connectivity, indent=2).encode()
    manifest = {'version': 1, 'mode': 'fixture' if fixture else 'production', 'release': '26.10',
                'disk': data['disk'], 'frp_server': data['frp']['serverAddr'],
                'frp_port': data['frp']['serverPort'], 'frpc_remote_sha256': data['frpc_sha256'], 'frpc_location': 'remote-only',
                'files': {name.removeprefix('payload/'): hashlib.sha256(value).hexdigest()
                          for name, value in files.items() if name.startswith('payload/')}}
    files['payload/manifest.json'] = json.dumps(manifest, sort_keys=True, indent=2).encode()
    ai = {'version': 1, 'refresh-installer': {'update': False},
          'source': {'id': 'ubuntu-server', 'search_drivers': False},
          'locale': 'en_US.UTF-8', 'keyboard': {'layout': 'us'}, 'timezone': 'Asia/Tokyo',
          'early-commands': ['sh /cdrom/spring-reset/payload/bootstrap.sh'],
          'network': network,
          'storage': {'layout': {'name': 'direct', 'match': {'path': data['disk']['path']}}},
          'identity': {'hostname': data['hostname'], 'username': 'springadmin', 'password': '!'},
          'ssh': {'install-server': True, 'authorized-keys': [admin_public.decode().strip()], 'allow-pw': False},
          'apt': {'geoip': False, 'fallback': 'offline-install'},
          'updates': 'security',
          'late-commands': [
              'mkdir -p /target/opt/reset-debs',
              'cp /cdrom/spring-reset/payload/debs/*.deb /target/opt/reset-debs/',
              'curtin in-target -- sh -c "cp /opt/reset-debs/*.deb /var/cache/apt/archives/; DEBIAN_FRONTEND=noninteractive apt-get -y --no-download install /var/cache/apt/archives/*.deb"',
              'python3 /cdrom/spring-reset/payload/install_target.py /cdrom/spring-reset/payload',
              'curtin in-target -- apt-get clean',
              'rm -rf /target/opt/reset-debs'],
          'shutdown': 'reboot'}
    files['seed/user-data'] = ('#cloud-config\n' + yaml.safe_dump({'autoinstall': ai}, sort_keys=False)).encode()
    files['seed/meta-data'] = b'instance-id: springmonkey-reset-26-10\n'
    # Initial seed is offline; early-commands installs wpasupplicant before applying Wi-Fi.
    files['seed/network-config'] = b'version: 2\nethernets: {}\n'
    private = {'admin_private': admin_private.decode(), 'host_public': host_public.decode()}
    return files, private


def collect_remote(host, port, password_file):
    import paramiko
    client = paramiko.SSHClient()
    client.load_system_host_keys(str(Path.home() / '.ssh/known_hosts'))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        password = Path(password_file).read_text(encoding='utf-8-sig').strip().splitlines()[0]
        client.connect(host, port=port, username='root', password=password, look_for_keys=False,
                       allow_agent=False, timeout=12, auth_timeout=12)
        stdin, stdout, stderr = client.exec_command('PYTHONDONTWRITEBYTECODE=1 python3 -', timeout=60)
        stdin.write((HERE / 'collect_remote.py').read_text()); stdin.channel.shutdown_write()
        raw = stdout.read()
        if stdout.channel.recv_exit_status(): raise ValueError('remote_collection_failed')
        data = json.loads(raw)
        if 'collection_error' in data: raise ValueError('remote_collection_failed')
        return data
    finally:
        client.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--debs', required=True, type=Path)
    ap.add_argument('--host')
    ap.add_argument('--port', type=int, default=8822)
    ap.add_argument('--password-file', type=Path)
    ap.add_argument('--fixture', action='store_true')
    ap.add_argument('--frpc-sha256')
    ap.add_argument('--refresh', action='store_true')
    ap.add_argument('--remote-frp-manifest', type=Path)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    debs = {p.name: p.read_bytes() for p in args.debs.glob('*.deb')}
    if args.fixture:
        data = {'hostname': 'reset-fixture', 'wifi': {'mac': '02:00:00:00:00:09', 'ssid': 'TEST ONLY wifi: # unicode 日本語', 'password': 'fixture-only-pass'},
                'disk': {'path': '/dev/vda', 'bytes': 21474836480, 'gpt_id': 'D9DDF93A-BBAB-4DCA-80BE-1691497BD571', 'serial': 'RESETFIXTURE'},
                'frp': {'serverAddr': '10.0.2.2', 'serverPort': 17000,
                        'auth': {'method': 'token', 'token': 'fixture-only-token'}, 'loginFailExit': False,
                        'proxies': [{'name': 'fixture-ssh', 'type': 'tcp', 'localIP': '127.0.0.1', 'localPort': 22, 'remotePort': 16022}]}}
        if not args.frpc_sha256 or len(args.frpc_sha256) != 64: raise ValueError('remote_frpc_hash_required')
        data['frpc_sha256'] = args.frpc_sha256
        keys = None
        if args.refresh:
            keys = tuple((args.output / n).read_bytes() for n in ['admin.key', 'payload/admin.pub', 'payload/ssh_host_ed25519_key', 'payload/ssh_host_ed25519_key.pub'])
        files, private = make_files(data, debs, fixture=True, keys=keys)
        for name, value in files.items():
            p = args.output / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(value)
        # Fixture-only arm. No production export or arming operation is exposed here.
        digest = hashlib.sha256(files['payload/manifest.json']).hexdigest()
        (args.output / 'payload/ARMED.json').write_text(json.dumps({'manifest_sha256': digest}))
        (args.output / 'admin.key').write_text(private['admin_private'])
        print('fixture_prepared')
    else:
        if sys.platform != 'win32': raise ValueError('windows_dpapi_required')
        import win32crypt
        keys = None
        if args.refresh:
            archive = win32crypt.CryptUnprotectData((args.output / 'CONNECTIVITY_RECOVERY.dpapi').read_bytes(), None, None, None, 1)[1]
            with zipfile.ZipFile(io.BytesIO(archive)) as z:
                old = json.loads(z.read('payload/manifest.json'))
                wifi = yaml.safe_load(z.read('payload/network.yaml'))['network']['wifis']['resetwifi']
                ssid, access = next(iter(wifi['access-points'].items()))
                data = {'hostname': 'ubuntu-2625', 'wifi': {'mac': wifi['match']['macaddress'], 'ssid': ssid, 'password': access['password']},
                        'disk': old['disk'], 'frp': __import__('tomllib').loads(z.read('payload/frpc.toml').decode()),
                        'frpc_version': json.loads((args.output / 'RECOVERY_MANIFEST.json').read_text())['frpc_version'],
                        'frpc_sha256': old['frpc_remote_sha256']}
                keys = tuple(z.read(n) for n in ['private/admin.key', 'payload/admin.pub', 'payload/ssh_host_ed25519_key', 'payload/ssh_host_ed25519_key.pub'])
        else:
            data = collect_remote(args.host, args.port, args.password_file)
        if args.remote_frp_manifest:
            remote_frp = json.loads(args.remote_frp_manifest.read_text())
            if remote_frp.get('configuration_verify') != 'PASS': raise ValueError('remote_frp_not_verified')
            data['frpc_sha256'] = remote_frp['frpc_sha256']
            data['frpc_version'] = remote_frp['version']
        files, private = make_files(data, debs, keys=keys)
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, 'w', zipfile.ZIP_DEFLATED) as z:
            for name, value in files.items(): z.writestr(name, value)
            z.writestr('private/admin.key', private['admin_private'])
        raw = memory.getvalue()
        encrypted = win32crypt.CryptProtectData(raw, 'SpringMonkey reset recovery', None, None, None, 1)
        p = args.output / 'CONNECTIVITY_RECOVERY.dpapi'; p.write_bytes(encrypted)
        restored = win32crypt.CryptUnprotectData(p.read_bytes(), None, None, None, 1)[1]
        if restored != raw: raise ValueError('dpapi_roundtrip_failed')
        rejected = False
        try: win32crypt.CryptUnprotectData(encrypted[:-32] + bytes(32), None, None, None, 1)
        except Exception: rejected = True
        if not rejected: raise ValueError('corrupt_dpapi_not_rejected')
        manifest = {'state': 'UNARMED', 'release': '26.10', 'hostname': data['hostname'],
                    'frpc_version': data['frpc_version'], 'frpc_sha256': data['frpc_sha256'],
                    'frpc_location': 'remote-only', 'contains_frp_binary': False,
                    'encrypted_sha256': hashlib.sha256(encrypted).hexdigest(), 'encrypted_bytes': len(encrypted),
                    'dpapi_roundtrip': 'PASS', 'dpapi_corruption_rejected': 'PASS', 'file_count': len(files),
                    'host_public_key': private['host_public'].strip(),
                    'ssid_saved': True, 'psk_saved': True, 'ssh_proxy_count': 1}
        (args.output / 'RECOVERY_MANIFEST.json').write_text(json.dumps(manifest, indent=2))
        print('encrypted_unarmed_recovery_prepared')


if __name__ == '__main__':
    try: main()
    except Exception as e:
        print('prepare_FAIL_' + type(e).__name__, file=sys.stderr)
        raise SystemExit(1)
