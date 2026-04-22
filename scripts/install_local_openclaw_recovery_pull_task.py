#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install a Windows Scheduled Task that pulls the latest OpenClaw recovery bundle daily.")
    parser.add_argument("--task-name", default="SpringMonkey-OpenClaw-Recovery-Pull")
    parser.add_argument("--time", default="04:20")
    parser.add_argument(
        "--repo-root",
        default=Path(__file__).resolve().parent.parent,
        type=Path,
        help="SpringMonkey repository root",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    script = repo_root / "scripts" / "local_sync_openclaw_recovery_bundle.py"
    python_exe = Path(sys.executable).resolve()

    tr = f'"{python_exe}" "{script}" --repo-root "{repo_root}"'
    cmd = [
        "schtasks",
        "/Create",
        "/F",
        "/SC",
        "DAILY",
        "/TN",
        args.task_name,
        "/ST",
        args.time,
        "/TR",
        tr,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
