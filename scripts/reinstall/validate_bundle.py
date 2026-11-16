"""Validate decrypted material in a Linux tmpfs; never print configuration values."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
import io

import jsonschema
import yaml
from guard import check_manifest


def validate(root, schema_path, armed=False):
    payload = root / 'payload'
    manifest = check_manifest(payload)
    config = yaml.safe_load((root / 'seed/user-data').read_text())['autoinstall']
    schema = json.loads(Path(schema_path).read_text())
    jsonschema.validate(config, schema)
    if (payload / 'ARMED.json').exists() != armed:
        raise ValueError('unexpected_arming_state')
    network = yaml.safe_load((payload / 'network.yaml').read_text())
    if config['network'] != network['network'] or config['ssh']['allow-pw']:
        raise ValueError('connectivity_config_disagrees')
    frp = tomllib.loads((payload / 'frpc.toml').read_text())
    if len(frp['proxies']) != 1 or frp['proxies'][0]['localPort'] != 22:
        raise ValueError('unexpected_proxy')
    nroot = root / 'netplan-root'
    (nroot / 'etc/netplan').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(payload / 'network.yaml', nroot / 'etc/netplan/90-test.yaml')
    (nroot / 'etc/netplan/90-test.yaml').chmod(0o600)
    subprocess.run(['netplan', 'generate', '--root-dir', str(nroot)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    frpc_status = 'REMOTE_ONLY_NOT_EXECUTED'
    if (payload / 'frpc').exists():
        (payload / 'frpc').chmod(0o755)
        subprocess.run([str(payload / 'frpc'), 'verify', '-c', str(payload / 'frpc.toml')], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        frpc_status = 'PASS'
    (payload / 'ssh_host_ed25519_key').chmod(0o600)
    pub = subprocess.check_output(['ssh-keygen', '-y', '-f', str(payload / 'ssh_host_ed25519_key')]).strip()
    if pub != (payload / 'ssh_host_ed25519_key.pub').read_bytes().strip():
        raise ValueError('host_key_mismatch')
    subprocess.run(['sh', '-n', str(payload / 'bootstrap.sh')], check=True)
    print(json.dumps({'schema': 'PASS', 'payload_hashes': 'PASS', 'netplan_generate': 'PASS',
                      'frpc_verify': frpc_status, 'host_key_pair': 'PASS', 'bootstrap_syntax': 'PASS',
                      'armed': armed, 'release': manifest['release']}))


if __name__ == '__main__':
    try:
        if '--stdin-zip' in sys.argv:
            with tempfile.TemporaryDirectory(dir='/secure') as d:
                root = Path(d)
                with zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())) as z:
                    for info in z.infolist():
                        if Path(info.filename).is_absolute() or '..' in Path(info.filename).parts:
                            raise ValueError('unsafe_archive_member')
                    z.extractall(root)
                validate(root, sys.argv[1])
        else:
            with tempfile.TemporaryDirectory(dir='/run') as d:
                root = Path(d) / 'fixture'
                shutil.copytree(Path(sys.argv[1]), root)
                validate(root, sys.argv[2], armed=True)
    except Exception as e:
        stage = Path(e.cmd[0]).name if isinstance(e, subprocess.CalledProcessError) else 'configuration'
        print('bundle_validation_FAIL_' + type(e).__name__ + '_' + stage, file=sys.stderr)
        raise SystemExit(1)
