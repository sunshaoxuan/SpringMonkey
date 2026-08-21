#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def month_bounds(now: datetime) -> tuple[str, datetime, datetime]:
    current_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_end = current_start
    previous_start = (current_start - timedelta(days=1)).replace(day=1)
    return previous_start.strftime("%Y-%m"), previous_start, previous_end


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def export_previous_month_journal(
    archive_root: Path,
    now: datetime,
    *,
    journal_file: Path | None = None,
    journal_unit: str = "openclaw.service",
) -> Path:
    previous_month, start, end = month_bounds(now)
    target = archive_root / "journal" / f"openclaw-{previous_month}.journal.gz"
    if target.is_file() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    if journal_file is not None:
        raw = journal_file.read_bytes()
    else:
        proc = subprocess.run(
            [
                "journalctl",
                "-u",
                journal_unit,
                "--since",
                start.strftime("%Y-%m-%d %H:%M:%S"),
                "--until",
                end.strftime("%Y-%m-%d %H:%M:%S"),
                "--no-pager",
            ],
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or b"journalctl failed").decode("utf-8", errors="replace"))
        raw = proc.stdout
    with gzip.open(temp, "wb", compresslevel=9) as output:
        output.write(raw)
    with gzip.open(temp, "rb") as verified:
        verified.read()
    temp.replace(target)
    return target


def run_retention(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    today = now.strftime("%Y-%m-%d")
    state = load_state(args.state_file)
    if not args.force and state.get("last_success_date") == today:
        return {"status": "already_completed", "date": today}

    journal_archive = export_previous_month_journal(
        args.archive_root,
        now,
        journal_file=args.journal_file,
        journal_unit=args.journal_unit,
    )
    retention_script = Path(args.repo_root) / "scripts" / "openclaw" / "monthly_log_retention.py"
    command = [
        sys.executable,
        str(retention_script),
        "--archive-root",
        str(args.archive_root),
        "--min-free-percent",
        str(args.min_free_percent),
    ]
    for source in args.source or []:
        command.extend(["--source", str(source)])
    proc = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "monthly log retention failed").strip())

    vacuum = {"status": "skipped_fixture"}
    if args.journal_file is None:
        vacuum_proc = subprocess.run(
            ["journalctl", f"--vacuum-time={args.journal_online_days}d"],
            capture_output=True,
            text=True,
            timeout=args.timeout,
            check=False,
        )
        vacuum = {
            "status": "completed" if vacuum_proc.returncode == 0 else "failed",
            "returncode": vacuum_proc.returncode,
            "output": (vacuum_proc.stdout or vacuum_proc.stderr or "").strip()[-1000:],
        }
        if vacuum_proc.returncode != 0:
            raise RuntimeError(vacuum["output"] or "journal vacuum failed")

    result = {
        "status": "completed",
        "date": today,
        "journal_archive": str(journal_archive),
        "retention_output": proc.stdout.strip(),
        "journal_vacuum": vacuum,
    }
    write_state(args.state_file, {"last_success_date": today, "last_result": result})
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenClaw log retention at most once per calendar day.")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, default=Path("/var/backups/openclaw-log-archive"))
    parser.add_argument("--source", action="append", type=Path)
    parser.add_argument("--journal-file", type=Path)
    parser.add_argument("--journal-unit", default="openclaw.service")
    parser.add_argument("--journal-online-days", type=int, default=35)
    parser.add_argument("--min-free-percent", type=float, default=10.0)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run_retention(args, datetime.now().astimezone())
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
