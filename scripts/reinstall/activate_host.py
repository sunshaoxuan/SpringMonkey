"""Prepare a one-shot RAM installer boot on the authorized original host.

This command stages boot files only. It never reboots or formats a disk.
Run only after the isolated same-disk installation has passed.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from guard import check_disk, check_manifest

ROOT = Path('/srv/springmonkey-reset-prep-20261116')


def main():
    if os.geteuid() != 0 or subprocess.check_output(['hostname'], text=True).strip() != 'ubuntu-2625':
        raise ValueError('authorized_original_host_required')
    validation = json.loads((ROOT / 'RAM_INSTALL_VALIDATION.json').read_text())
    if validation.get('result') != 'PASS' or validation.get('initramfs_release_marker') != 'PASS':
        raise ValueError('isolated_same_disk_validation_missing')
    payload = ROOT / 'production-next/payload'
    manifest = check_manifest(payload)
    if manifest['mode'] != 'production':
        raise ValueError('production_payload_required')
    fixture = ROOT / 'fixture-next/payload'
    for name in ['bootstrap.sh', 'guard.py', 'install_target.py', 'network_ready.py',
                 'reset-connectivity-ready.service', 'tailscaled-recovery.service', 'initramfs-release.sh', 'persist_failure.py']:
        if (payload / name).read_bytes() != (fixture / name).read_bytes():
            raise ValueError('tested_common_source_mismatch')
        if validation.get('tested_common_source_hashes', {}).get(name) != manifest['files'][name]:
            raise ValueError('validated_source_hash_mismatch')
        if hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest() != manifest['files'][name]:
            raise ValueError('pinned_repository_source_mismatch')
    with (ROOT / 'vm/initrd-release').open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != validation['initrd_sha256']:
            raise ValueError('tested_boot_initrd_mismatch')
    disk = manifest['disk']
    actual = {'path': disk['path'],
              'bytes': int(subprocess.check_output(['blockdev', '--getsize64', disk['path']], text=True)),
              'serial': subprocess.check_output(['lsblk', '-dn', '-o', 'SERIAL', disk['path']], text=True).strip(),
              'gpt_id': json.loads(subprocess.check_output(['sfdisk', '--json', disk['path']], text=True))['partitiontable']['id']}
    check_disk(disk, actual)
    if 'SecureBoot enabled' not in subprocess.check_output(['mokutil', '--sb-state'], text=True):
        raise ValueError('secure_boot_required')
    ts = json.loads(subprocess.check_output(['tailscale', 'status', '--json'], text=True))
    if ts.get('BackendState') != 'Running' or not ts.get('Self', {}).get('Online'):
        raise ValueError('original_tailscale_not_online')
    for name in ['tailscale', 'tailscaled', 'tailscale-state.tar.gz']:
        if name not in manifest['files']:
            raise ValueError('authenticated_identity_not_staged')
    (payload / 'ARMED.json').write_text(json.dumps({'manifest_sha256': hashlib.sha256((payload / 'manifest.json').read_bytes()).hexdigest()}))
    (payload / 'ARMED.json').chmod(0o600)
    iso = ROOT / 'production-installer.iso'
    if iso.exists():
        raise ValueError('production_iso_already_exists_review_prior_run')
    base = ['docker', 'run', '--rm', '--network=none', '--mount', f'type=bind,source={ROOT},target=/task',
            'spring-reset-validation:20261116', 'xorriso']
    with (ROOT / 'production-iso-build.log').open('w') as log:
        subprocess.run(base + ['-indev', '/task/ubuntu-26.10-live-server-amd64.iso',
                              '-outdev', '/task/production-installer.iso', '-boot_image', 'any', 'replay',
                              '-map', '/task/production-next/payload', '/spring-reset/payload',
                              '-map', '/task/production-next/seed', '/spring-reset/seed',
                              '-chmod', '0755', '/spring-reset/payload/frpc', '--'],
                       check=True, stdout=log, stderr=log, timeout=240)
    iso.chmod(0o600)
    boot = Path('/boot/spring-reset-live'); boot.mkdir(mode=0o755, exist_ok=False)
    # Use the isolated boot's official signed kernel and tested initramfs.
    for name in ['vmlinuz', 'initrd']:
        source = 'initrd-release' if name == 'initrd' else name
        shutil.copyfile(ROOT / 'vm' / source, boot / name)
        (boot / name).chmod(0o644)
    grub = '''#!/bin/sh
exec tail -n +3 $0
menuentry 'SpringMonkey Ubuntu 26.10 reset' --id springmonkey-reset {
    search --no-floppy --file --set=root /srv/springmonkey-reset-prep-20261116/production-installer.iso
    linux /boot/spring-reset-live/vmlinuz boot=casper iso-scan/filename=/srv/springmonkey-reset-prep-20261116/production-installer.iso toram spring-reset-release noprompt noeject autoinstall ds=nocloud\\;s=/cdrom/spring-reset/seed/ panic=30 ---
    initrd /boot/spring-reset-live/initrd
}
'''
    shutil.copyfile('/boot/grub/grub.cfg', ROOT / 'original-grub.cfg')
    entry = Path('/etc/grub.d/41_springmonkey_reset')
    if entry.exists():
        raise ValueError('reset_boot_entry_already_exists')
    entry.write_text(grub); entry.chmod(0o755)
    with (ROOT / 'grub-prepare.log').open('w') as log:
        subprocess.run(['update-grub'], stdout=log, stderr=log, check=True, timeout=90)
    subprocess.run(['grub-script-check', '/boot/grub/grub.cfg'], check=True, timeout=15)
    with iso.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    result = {'state': 'BOOT_PREPARED_NOT_SCHEDULED', 'iso_sha256': digest,
              'manifest_sha256': hashlib.sha256((payload / 'manifest.json').read_bytes()).hexdigest(),
              'disk_identity': 'PASS', 'isolated_same_disk_install': 'PASS',
              'common_tested_sources': 'PASS', 'original_tailscale_online': True,
              'default_boot_unchanged': True,
              'limitations': ['No independent firmware console or hardware watchdog']}
    (ROOT / 'PRODUCTION_BOOT_PREPARATION.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('activation_FAIL_' + type(e).__name__, file=sys.stderr)
        raise SystemExit(1)
