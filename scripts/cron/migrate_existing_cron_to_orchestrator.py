#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
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
    return parser.parse_args()


def load_jobs(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("jobs", [])


def build_upsert_args(job: dict, message_file: Path) -> list[str]:
    schedule = job.get("schedule", {})
    payload = job.get("payload", {})
    delivery = job.get("delivery", {})
    args = [
        sys.executable,
        str(Path(__file__).with_name("upsert_generic_cron_job.py")),
        "--name",
        job["name"],
        "--expr",
        schedule["expr"],
        "--tz",
        schedule.get("tz", "Asia/Tokyo"),
        "--message-file",
        str(message_file),
        "--delivery-channel",
        delivery["channel"],
        "--delivery-to",
        delivery["to"],
        "--delivery-account-id",
        delivery.get("accountId", "default"),
        "--model",
        payload.get("model", "ollama/qwen3:14b"),
        "--thinking",
        payload.get("thinking", "low"),
        "--timeout-seconds",
        str(payload.get("timeoutSeconds", 1800)),
        "--light-context",
        "true" if payload.get("lightContext", True) else "false",
        "--execution-depth",
        "staged",
        "--orchestrator-mode",
        "required",
    ]
    if job.get("description"):
        args.extend(["--description", job["description"]])
    if not bool(job.get("enabled", True)):
        args.append("--disabled")
    return args


def main() -> int:
    args = parse_args()
    jobs = {job.get("name"): job for job in load_jobs(Path(args.jobs_file))}
    targets = args.only or TARGET_ORDER
    migrated: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="cron_orchestrator_migration_") as tmp:
        tmpdir = Path(tmp)
        for name in targets:
            job = jobs.get(name)
            if not job:
                migrated.append({"name": name, "status": "missing"})
                continue
            message = job.get("payload", {}).get("message", "")
            wrapped, depth = apply_task_creation_policy(
                message,
                requested_depth="staged",
                orchestrator_mode="required",
            )
            if wrapped == message:
                migrated.append({"name": name, "status": "already_wrapped", "depth": depth})
                continue
            msg_file = tmpdir / f"{name}.prompt.txt"
            msg_file.write_text(wrapped, encoding="utf-8")
            if args.dry_run:
                migrated.append({"name": name, "status": "would_migrate", "depth": depth})
                continue
            proc = subprocess.run(build_upsert_args(job, msg_file), capture_output=True, text=True, encoding="utf-8")
            if proc.returncode != 0:
                raise SystemExit(f"failed to migrate {name}: {(proc.stderr or proc.stdout).strip()}")
            migrated.append({"name": name, "status": "migrated", "depth": depth})
    print(json.dumps({"jobs": migrated}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
