"""Restore only explicit connectivity files inside the installer's /target."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from guard import check_manifest


def restore(root, target):
    root, target = Path(root).resolve(), Path(target).resolve()
    if str(target) != '/target' or target.is_symlink() or not (target / 'etc/os-release').is_file():
        raise ValueError('installer_target_required')
    manifest = check_manifest(root)
    def put(source, dest, mode):
        p = target / dest.lstrip('/')
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / source, p)
        p.chmod(mode)
    # Prevent cloud-init or installer-generated duplicates overriding this profile.
    for p in (target / 'etc/netplan').glob('*.yaml'):
        p.unlink()
    put('network.yaml', '/etc/netplan/90-reset-connectivity.yaml', 0o600)
    put('frpc', '/usr/local/bin/frpc', 0o755)
    put('frpc.toml', '/etc/frp/frpc.toml', 0o640)
    put('frpc.service', '/etc/systemd/system/frpc.service', 0o644)
    put('network_ready.py', '/usr/local/sbin/reset-network-ready.py', 0o755)
    put('reset-connectivity-ready.service', '/etc/systemd/system/reset-connectivity-ready.service', 0o644)
    put('connectivity.json', '/etc/reset-connectivity.json', 0o600)
    put('admin.pub', '/etc/reset-admin.pub', 0o644)
    put('ssh_host_ed25519_key', '/etc/ssh/ssh_host_ed25519_key', 0o600)
    put('ssh_host_ed25519_key.pub', '/etc/ssh/ssh_host_ed25519_key.pub', 0o644)
    p = target / 'etc/cloud/cloud.cfg.d/99-reset-network.cfg'
    p.write_text('network: {config: disabled}\nssh_deletekeys: false\n')
    p = target / 'etc/ssh/sshd_config.d/00-reset-key-only.conf'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\nPubkeyAuthentication yes\nHostKey /etc/ssh/ssh_host_ed25519_key\n')
    p = target / 'etc/sudoers.d/90-springadmin'
    p.write_text('springadmin ALL=(ALL) NOPASSWD:ALL\n'); p.chmod(0o440)
    if subprocess.run(['chroot', str(target), 'id', '-u', 'frp'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        subprocess.run(['chroot', str(target), 'useradd', '--system', '--no-create-home', '--shell', '/usr/sbin/nologin', 'frp'], check=True)
    subprocess.run(['chroot', str(target), 'chown', 'root:frp', '/etc/frp/frpc.toml'], check=True)
    (target / 'run/sshd').mkdir(parents=True, exist_ok=True)
    subprocess.run(['netplan', 'generate', '--root-dir', str(target)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['chroot', str(target), '/usr/sbin/sshd', '-t'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    units = ['NetworkManager', 'systemd-resolved', 'ssh', 'reset-connectivity-ready', 'frpc']
    if (root / 'tailscale').is_file() and (root / 'tailscaled').is_file() and (root / 'tailscale-state.tar.gz').is_file():
        import tarfile
        put('tailscale', '/usr/bin/tailscale', 0o755)
        put('tailscaled', '/usr/sbin/tailscaled', 0o755)
        with tarfile.open(root / 'tailscale-state.tar.gz') as archive:
            for entry in archive.getmembers():
                if entry.isfile() and entry.name.startswith('var/lib/tailscale/') and '..' not in Path(entry.name).parts:
                    p = target / entry.name; p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(archive.extractfile(entry).read()); p.chmod(0o600)
        (target / 'var/lib/tailscale').chmod(0o700)
        put('tailscaled-recovery.service', '/etc/systemd/system/tailscaled.service', 0o644)
        units.append('tailscaled')
    elif manifest['mode'] == 'production':
        raise ValueError('preserved_tailscale_payload_missing')
    subprocess.run(['systemctl', '--root', str(target), 'enable', *units], check=True)
    subprocess.run(['systemctl', '--root', str(target), 'disable', 'systemd-networkd-wait-online.service'], check=True)
    print('target_connectivity_restore_PASS')


if __name__ == '__main__':
    try:
        restore(sys.argv[1], '/target')
    except Exception as e:
        print('target_restore_FAIL_' + type(e).__name__, file=sys.stderr)
        raise SystemExit(1)
