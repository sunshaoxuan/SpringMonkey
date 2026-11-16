"""Installer preflight; contains no partitioning or filesystem mutation commands."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys


def check_manifest(root):
    manifest = json.loads((root / 'manifest.json').read_text())
    for name, digest in manifest['files'].items():
        p = root / name
        if Path(name).is_absolute() or '..' in Path(name).parts or p.is_symlink():
            raise ValueError('unsafe_payload_path')
        if hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise ValueError('payload_checksum_mismatch')
    if (root / 'frpc').exists() and manifest.get('frpc_remote_sha256'):
        if hashlib.sha256((root / 'frpc').read_bytes()).hexdigest() != manifest['frpc_remote_sha256']:
            raise ValueError('remote_frpc_checksum_mismatch')
    return manifest


def check_disk(expected, actual):
    for field in ['path', 'bytes', 'serial', 'gpt_id']:
        if expected.get(field) != actual.get(field):
            raise ValueError('disk_identity_mismatch_' + field)


def release_install_source(disk):
    if subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE', '/cdrom'], text=True).strip() != 'tmpfs':
        raise ValueError('installation_media_not_in_ram')
    tree = json.loads(subprocess.check_output(['lsblk', '-J', '-p', '-o', 'NAME', disk], text=True))
    def names(items):
        return {name for item in items for name in ({item['name']} | names(item.get('children', [])))}
    devices = names(tree['blockdevices'])
    swaps = [line.split()[0] for line in Path('/proc/swaps').read_text().splitlines()[1:]]
    if any(s in devices for s in swaps):
        raise ValueError('target_disk_swap_active')
    loops = json.loads(subprocess.check_output(['losetup', '--list', '--json', '--output', 'NAME,BACK-FILE'], text=True))
    for loop in loops.get('loopdevices', []):
        if (loop.get('back-file') or '').startswith('/isodevice/'):
            if subprocess.run(['findmnt', '-rn', '-S', loop['name']], stdout=subprocess.DEVNULL).returncode == 0:
                raise ValueError('installation_iso_loop_still_mounted')
            subprocess.run(['losetup', '--detach', loop['name']], check=True)
    mounted = subprocess.run(['findmnt', '-n', '-o', 'SOURCE', '/isodevice'], text=True, capture_output=True)
    if mounted.returncode == 0:
        if mounted.stdout.strip() not in devices:
            raise ValueError('unexpected_iso_source_disk')
        subprocess.run(['umount', '/isodevice'], check=True)
    # Linux rejects exclusive block-device access while a partition is in use.
    fd = os.open(disk, os.O_RDONLY | os.O_EXCL)
    os.close(fd)
    memory = {k: int(v.split()[0]) for k, v in (line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())}
    if memory['MemAvailable'] < 1536 * 1024:
        raise ValueError('insufficient_ram_after_media_copy')
    Path('/run/reset-media-released').write_text('RAM_MEDIA_TARGET_DISK_EXCLUSIVE_PASS\n')


def main():
    root = Path(sys.argv[1]).resolve()
    manifest = check_manifest(root)
    if not (root / 'frpc').is_file():
        raise ValueError('remote_frpc_not_staged')
    arm = root / 'ARMED.json'
    expected_hash = hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest()
    if not arm.is_file() or json.loads(arm.read_text()).get('manifest_sha256') != expected_hash:
        raise ValueError('package_not_armed')
    if not Path('/sys/firmware/efi').exists():
        raise ValueError('uefi_required')
    disk = manifest['disk']
    actual = {'path': disk['path'],
              'bytes': int(subprocess.check_output(['blockdev', '--getsize64', disk['path']], text=True)),
              'serial': subprocess.check_output(['lsblk', '-dn', '-o', 'SERIAL', disk['path']], text=True).strip(),
              'gpt_id': json.loads(subprocess.check_output(['sfdisk', '--json', disk['path']], text=True))['partitiontable']['id']}
    check_disk(disk, actual)
    if manifest['mode'] == 'production' or manifest.get('require_ram_media'):
        release_install_source(disk['path'])
    if manifest['mode'] == 'production':
        state = subprocess.check_output(['mokutil', '--sb-state'], text=True)
        if 'SecureBoot enabled' not in state:
            raise ValueError('secure_boot_required')
        cfg = json.loads((root / 'connectivity.json').read_text())
        matches = [p for p in Path('/sys/class/net').iterdir()
                   if (p / 'address').read_text().strip().lower() == cfg['network_mac'].lower()]
        if len(matches) != 1 or not (matches[0] / 'wireless').exists():
            raise ValueError('expected_wifi_not_present')
        iface = matches[0].name
        status = subprocess.check_output(['nmcli', '-g', 'GENERAL.STATE', 'device', 'show', iface], text=True)
        routes = json.loads(subprocess.check_output(['ip', '-j', 'route', 'show', 'default'], text=True))
        if not status.startswith('100') or not any(r.get('dev') == iface for r in routes):
            raise ValueError('wifi_not_connected_with_route')
    socket.getaddrinfo(manifest['frp_server'], manifest['frp_port'])
    with socket.create_connection((manifest['frp_server'], manifest['frp_port']), timeout=10):
        pass
    subprocess.run([str(root / 'frpc'), 'verify', '-c', str(root / 'frpc.toml')],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=15)
    print('preflight_PASS')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('preflight_FAIL_' + type(e).__name__, file=sys.stderr)
        raise SystemExit(1)
