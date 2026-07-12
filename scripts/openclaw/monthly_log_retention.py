#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path


DEFAULT_SOURCES = (
    Path("/var/lib/openclaw/.openclaw/logs"),
    Path("/var/lib/openclaw/repos/SpringMonkey/implementation_run_logs"),
    Path("/var/log/openclaw"),
    Path("/var/log/openclaw-maint"),
)


def month_key(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m")


def source_slug(path: Path) -> str:
    normalized = str(path).replace("\\", "/").strip("/")
    slug = normalized.replace("/", "__") or "root"
    if len(slug) <= 80:
        return slug
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"{path.name or 'root'}-{digest}"


def free_percent(path: Path) -> float:
    usage = shutil.disk_usage(path)
    return usage.free * 100.0 / usage.total


def archive_source(source: Path, archive_root: Path, current_month: str, dry_run: bool = False) -> list[Path]:
    if not source.is_dir():
        return []
    groups: dict[str, list[Path]] = {}
    archive_root_resolved = archive_root.resolve()
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        try:
            if path.resolve().is_relative_to(archive_root_resolved):
                continue
        except ValueError:
            pass
        key = month_key(path.stat().st_mtime)
        if key < current_month:
            groups.setdefault(key, []).append(path)

    written: list[Path] = []
    for key, paths in sorted(groups.items()):
        archive = archive_root / source_slug(source) / f"{key}.zip"
        existing: set[str] = set()
        if archive.exists():
            with zipfile.ZipFile(archive) as current:
                existing = set(current.namelist())
        pending = [(path, path.relative_to(source).as_posix()) for path in paths]
        pending = [(path, name) for path, name in pending if name not in existing]
        if not pending:
            for path in paths:
                if not dry_run:
                    path.unlink(missing_ok=True)
            continue
        if dry_run:
            written.append(archive)
            continue
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "a", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
            for path, name in pending:
                output.write(path, name)
        with zipfile.ZipFile(archive) as verified:
            names = set(verified.namelist())
            if any(name not in names for _path, name in pending):
                raise RuntimeError(f"archive verification failed: {archive}")
        for path in paths:
            path.unlink(missing_ok=True)
        written.append(archive)
    return written


def prune_oldest_archives(archive_root: Path, min_free_percent: float, dry_run: bool = False) -> list[Path]:
    deleted: list[Path] = []
    archives = sorted(
        [*archive_root.rglob("*.zip"), *archive_root.rglob("*.journal.gz")],
        key=lambda path: (path.stat().st_mtime, str(path)),
    ) if archive_root.exists() else []
    for archive in archives:
        if free_percent(archive_root) >= min_free_percent:
            break
        deleted.append(archive)
        if not dry_run:
            archive.unlink(missing_ok=True)
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, default=Path("/var/backups/openclaw-log-archive"))
    parser.add_argument("--source", action="append", type=Path)
    parser.add_argument("--min-free-percent", type=float, default=10.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    current_month = datetime.now().strftime("%Y-%m")
    sources = tuple(args.source) if args.source else DEFAULT_SOURCES
    args.archive_root.mkdir(parents=True, exist_ok=True)
    archived: list[Path] = []
    for source in sources:
        archived.extend(archive_source(source, args.archive_root, current_month, args.dry_run))
    deleted = prune_oldest_archives(args.archive_root, args.min_free_percent, args.dry_run)
    print(f"current_month={current_month}")
    print(f"free_percent={free_percent(args.archive_root):.2f}")
    for path in archived:
        print(f"archived={path}")
    for path in deleted:
        print(f"deleted_oldest_archive={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
