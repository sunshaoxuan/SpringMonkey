#!/usr/bin/env python3
"""Upgrade only ccnode:49530 URLs, preserving model/auth and other endpoints."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

OLD_URL = 'http://ccnode.briconbric.com:49530/v1'
NEW_URL = 'https://ccnode.briconbric.com:49530/v1'


def upgrade_json(value):
    if isinstance(value, dict):
        return {key: upgrade_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [upgrade_json(item) for item in value]
    if isinstance(value, str) and (value == OLD_URL or value.startswith(OLD_URL + '/')):
        return NEW_URL + value[len(OLD_URL):]
    return value


def upgrade_env(text: str) -> str:
    lines = []
    for line in text.splitlines(keepends=True):
        key, separator, _ = line.partition('=')
        if separator and key.strip().removeprefix('export ').strip().endswith('BASE_URL'):
            line = line.replace(OLD_URL, NEW_URL)
        lines.append(line)
    return ''.join(lines)


def write_preserving_metadata(path: Path, content: str, stamp: str) -> None:
    metadata = path.stat()
    backup = path.with_name(path.name + '.bak-https-' + stamp)
    shutil.copy2(path, backup)
    os.chown(backup, metadata.st_uid, metadata.st_gid)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.' + path.name + '-', delete=False) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), metadata.st_mode & 0o7777)
            os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def migrate(*, roots: tuple[Path, ...], env_path: Path, guard_path: Path,
            apply: bool = False) -> dict:
    changes = {}
    for root in roots:
        paths = [root / 'openclaw.json', *sorted(root.glob('agents/*/agent/models.json'))]
        for path in paths:
            if not path.is_file():
                continue
            original = path.read_text(encoding='utf-8')
            data = json.loads(original)
            updated = upgrade_json(data)
            if updated != data:
                changes[path] = json.dumps(updated, ensure_ascii=False, indent=2) + '\n'
    if env_path.is_file():
        original = env_path.read_text(encoding='utf-8')
        updated = upgrade_env(original)
        if updated != original:
            changes[env_path] = updated
    if guard_path.is_file():
        original = guard_path.read_text(encoding='utf-8')
        updated = original.replace(OLD_URL, NEW_URL)
        if updated != original:
            changes[guard_path] = updated
    if apply:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        for path, content in changes.items():
            write_preserving_metadata(path, content, stamp)
    return {'applied': apply, 'changed_files': [str(path) for path in changes],
            'base_url': NEW_URL}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    result = migrate(roots=(Path('/var/lib/openclaw/.openclaw'), Path('/root/.openclaw')),
                     env_path=Path('/etc/openclaw/openclaw.env'),
                     guard_path=Path('/usr/local/lib/openclaw/ensure_model_auth_profiles.sh'),
                     apply=args.apply)
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
