#!/usr/bin/env python3
"""Remove TimesCar entries from the host's direct Discord cron only."""

import hashlib
import os
import re
import stat
from pathlib import Path
from tempfile import NamedTemporaryFile


CRON_FILE = Path('/etc/cron.d/openclaw-direct-discord')
BACKUP_DIR = Path('/var/backups')
ENTRY = re.compile(rb'\b(?:direct_cron_to_discord\.py\s+--name\s+timescar-[a-z0-9-]+\b|scripts/timescar/)')
CRON_COMMAND = re.compile(rb'^\s*(?:[0-9*/,\-]+\s+(?:\S+\s+){4}|@[a-z]+\s+)\S+\s+')


def remove_entries(data: bytes) -> tuple[bytes, int]:
    kept = []
    removed = 0
    for line in data.splitlines(keepends=True):
        if not line.lstrip().startswith(b'#') and CRON_COMMAND.match(line) and ENTRY.search(line):
            removed += 1
        else:
            kept.append(line)
    return b''.join(kept), removed


def apply(cron_file: Path, backup_dir: Path) -> tuple[int, Path | None]:
    metadata = cron_file.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f'Expected a regular cron file: {cron_file}')
    before = cron_file.read_bytes()
    after, removed = remove_entries(before)
    if not removed:
        return 0, None

    with NamedTemporaryFile(prefix='openclaw-direct-discord.pre-timescar-stop.',
                            dir=backup_dir, delete=False) as backup:
        backup.write(before)
        backup.flush()
        os.fsync(backup.fileno())

    tmp = NamedTemporaryFile(prefix='.timescar-stop.', dir=cron_file.parent, delete=False)
    staged = Path(tmp.name)
    try:
        with tmp:
            tmp.write(after)
            tmp.flush()
            os.fchown(tmp.fileno(), metadata.st_uid, metadata.st_gid)
            os.fchmod(tmp.fileno(), stat.S_IMODE(metadata.st_mode))
            os.fsync(tmp.fileno())
        current = cron_file.lstat()
        if ((current.st_dev, current.st_ino, current.st_ctime_ns) !=
                (metadata.st_dev, metadata.st_ino, metadata.st_ctime_ns) or
                cron_file.read_bytes() != before):
            raise RuntimeError('Cron file changed during preparation; original left in place')
        os.replace(staged, cron_file)
    finally:
        staged.unlink(missing_ok=True)
    if cron_file.read_bytes() != after:
        raise RuntimeError('Post-write cron content did not match')
    return removed, Path(backup.name)


if __name__ == '__main__':
    count, backup_path = apply(CRON_FILE, BACKUP_DIR)
    sha = hashlib.sha256(CRON_FILE.read_bytes()).hexdigest()
    print(f'removed={count} active_cron_sha256={sha} backup={backup_path or "none"}')
