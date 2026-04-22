#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import os
from pathlib import Path
import re
import subprocess
import sys


PATTERN = re.compile(r"openclaw-recovery-(\d{8})-(\d{6})\.tar\.gz$")
KEEP_DAILY = 7
KEEP_WEEKLY = 8
KEEP_MONTHLY = 6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pull the latest OpenClaw recovery bundle to the local machine and prune older local copies.")
    parser.add_argument(
        "--repo-root",
        default=Path(__file__).resolve().parent.parent,
        type=Path,
        help="SpringMonkey repository root",
    )
    parser.add_argument(
        "--local-dir",
        default=Path(__file__).resolve().parent.parent / "var" / "recovery-bundles",
        type=Path,
        help="Local directory to store downloaded recovery bundles",
    )
    return parser.parse_args()


def parse_stamp(path: Path) -> datetime | None:
    match = PATTERN.fullmatch(path.name)
    if not match:
        return None
    return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")


def prune_local_bundles(root: Path) -> None:
    items: list[tuple[datetime, Path]] = []
    for path in root.glob("openclaw-recovery-*.tar.gz"):
        stamp = parse_stamp(path)
        if stamp is not None:
            items.append((stamp, path))
    items.sort(reverse=True)

    keep: set[Path] = set()

    for stamp, path in items[:KEEP_DAILY]:
        keep.add(path)

    weekly: dict[tuple[int, int], list[Path]] = defaultdict(list)
    for stamp, path in items:
        weekly[(stamp.isocalendar().year, stamp.isocalendar().week)].append(path)
    for _, paths in sorted(weekly.items(), reverse=True)[:KEEP_WEEKLY]:
        keep.add(paths[0])

    monthly: dict[tuple[int, int], list[Path]] = defaultdict(list)
    for stamp, path in items:
        monthly[(stamp.year, stamp.month)].append(path)
    for _, paths in sorted(monthly.items(), reverse=True)[:KEEP_MONTHLY]:
        keep.add(paths[0])

    for _, path in items:
        if path not in keep:
            path.unlink(missing_ok=True)


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    local_dir = args.local_dir.resolve()
    local_dir.mkdir(parents=True, exist_ok=True)

    env = dict(**{"OPENCLAW_RECOVERY_BUNDLE_DIR": str(local_dir)})
    proc = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "remote_create_openclaw_recovery_bundle.py")],
        cwd=str(repo_root),
        env={**os.environ, **env},
        capture_output=True,
        text=True,
    )
    sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        return proc.returncode

    prune_local_bundles(local_dir)
    kept = sorted(path.name for path in local_dir.glob("openclaw-recovery-*.tar.gz"))
    for name in kept:
        print(f"LOCAL_KEEP {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
