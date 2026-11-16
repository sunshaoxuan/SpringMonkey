"""Save a pre-ack failure code to the identity-checked original root, then unmount."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from guard import check_disk, check_manifest, disk_identity

STAGING = Path('srv/springmonkey-reset-prep-20261116')


def persist(payload, phase, code):
    payload = Path(payload)
    if Path('/run/reset-live-ssh-confirmed').exists():
        raise ValueError('cannot_write_old_root_after_ack')
    manifest = check_manifest(payload)
    if manifest['mode'] == 'production' and subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE', '/'], text=True).strip() != 'overlay':
        raise ValueError('live_installer_required')
    disk = manifest['disk']; check_disk(disk, disk_identity(disk['path']))
    tree = json.loads(subprocess.check_output(['lsblk', '-J', '-p', '-o', 'NAME,FSTYPE', disk['path']], text=True))
    candidates = []
    def visit(items):
        for item in items:
            if item.get('fstype') == 'ext4': candidates.append(item['name'])
            visit(item.get('children', []))
    visit(tree['blockdevices'])
    if len(candidates) != 1:
        raise ValueError('original_ext4_root_not_unique')
    mount = Path('/run/reset-rollback-root'); mount.mkdir(mode=0o700, exist_ok=True)
    subprocess.run(['mount', '-t', 'ext4', '-o', 'rw,nosuid,nodev', candidates[0], str(mount)], check=True, timeout=30,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        destination = mount / STAGING
        if destination.is_symlink() or destination.stat().st_uid != 0 or stat.S_IMODE(destination.stat().st_mode) != 0o700:
            raise ValueError('protected_original_staging_required')
        original = destination / 'production-next/payload/manifest.json'
        digest = hashlib.sha256((payload / 'manifest.json').read_bytes()).hexdigest()
        if hashlib.sha256(original.read_bytes()).hexdigest() != digest:
            raise ValueError('original_manifest_binding_mismatch')
        reason = None
        log = Path('/run/reset-guard.log')
        if log.exists():
            # guard emits fixed validation codes, never configuration contents.
            reason = next((line.strip() for line in log.read_text().splitlines() if line.startswith('preflight_FAIL_')), None)
        record = {'phase': phase, 'exit_code': int(code), 'reason': reason, 'manifest_sha256': digest,
                  'recorded_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'install_acknowledged': False, 'original_disk_identity': 'PASS'}
        path = destination / 'LAST_LIVE_FAILURE.json'; temporary = destination / 'LAST_LIVE_FAILURE.tmp'
        with temporary.open('w') as f:
            temporary.chmod(0o600); json.dump(record, f, indent=2); f.flush(); os.fsync(f.fileno())
        os.replace(temporary, path)
        subprocess.run(['sync', '-f', str(destination)], check=True, timeout=15)
    finally:
        subprocess.run(['umount', str(mount)], check=True, timeout=30)
    print('pre_ack_failure_saved')


if __name__ == '__main__':
    try:
        persist(sys.argv[1], sys.argv[2], sys.argv[3])
    except Exception as e:
        print('failure_log_not_saved_' + type(e).__name__, file=sys.stderr)
        raise SystemExit(1)
