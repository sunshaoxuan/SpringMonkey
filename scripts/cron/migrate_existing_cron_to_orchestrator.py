#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import shutil
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from upsert_generic_cron_job import JOBS_PATH, apply_task_creation_policy


TARGET_ORDER = [
    "weather-report-jst-0700",
    "timescar-ask-cancel-next24h-2300",
    "timescar-ask-cancel-next24h-0000",
    "timescar-ask-cancel-next24h-0100",
    "timescar-ask-cancel-next24h-0700",
    "timescar-ask-cancel-next24h-0800",
    "timescar-daily-report-2200",
    "timescar-book-sat-3weeks",
    "timescar-extend-sun-3weeks",
    "news-digest-jst-0900",
    "news-digest-jst-1700",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wrap existing multi-step cron payloads with orchestrator policy.")
    parser.add_argument("--jobs-file", default=str(JOBS_PATH))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", action="append", help="Limit migration to one job name. Can be repeated.")
    parser.add_argument("--backup-suffix", default=".bak-orchestrator")
    return parser.parse_args()


def load_jobs(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("jobs", [])


def main() -> int:
    args = parse_args()
    jobs_path = Path(args.jobs_file)
    data = json.loads(jobs_path.read_text(encoding="utf-8"))
    jobs_list = data.get("jobs", [])
    jobs = {job.get("name"): job for job in jobs_list}
    targets = args.only or TARGET_ORDER
    migrated: list[dict] = []
    changed = False
    for name in targets:
        job = jobs.get(name)
        if not job:
            migrated.append({"name": name, "status": "missing"})
            continue
        payload = job.setdefault("payload", {})
        message = payload.get("message", "")
        wrapped, depth = apply_task_creation_policy(
            message,
            requested_depth="staged",
            orchestrator_mode="required",
        )
        if wrapped == message:
            migrated.append({"name": name, "status": "already_wrapped", "depth": depth})
            continue
        if args.dry_run:
            migrated.append({"name": name, "status": "would_migrate", "depth": depth})
            continue
        payload["message"] = wrapped
        changed = True
        migrated.append({"name": name, "status": "migrated", "depth": depth})
    backup = None
    if changed and not args.dry_run:
        backup = jobs_path.with_name(jobs_path.name + args.backup_suffix)
        shutil.copy2(jobs_path, backup)
        tmp = jobs_path.with_suffix(jobs_path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(jobs_path)
    print(json.dumps({"jobs": migrated, "backup": None if backup is None else str(backup)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
