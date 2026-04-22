#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


FAILURE_RE = r'Cron job "(?P<job>[^"]+)" failed: (?P<reason>.+)$'


def load_journal_text(args: argparse.Namespace) -> str:
    if args.journal_file:
        return Path(args.journal_file).read_text(encoding="utf-8", errors="replace")
    cmd = [
        "journalctl",
        "-u",
        args.journal_unit,
        "-n",
        str(args.tail),
        "--no-pager",
        "--output=short-iso",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout


def parse_failure_events(text: str) -> list[dict[str, str]]:
    import re

    events: list[dict[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.search(FAILURE_RE, line)
        if not match:
            continue
        job_name = match.group("job").strip()
        reason = match.group("reason").strip()
        key = hashlib.sha1(f"{job_name}|{reason}".encode("utf-8")).hexdigest()
        events.append(
            {
                "job_name": job_name,
                "reason": reason,
                "event_key": key,
                "raw_line": line,
            }
        )
    return events


def load_jobs_by_name(path: Path | None) -> dict[str, dict]:
    if path is None or not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    jobs = data.get("jobs", [])
    return {str(job.get("name")): job for job in jobs if job.get("name")}


def load_seen_state(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_seen_state(path: Path, payload: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def infer_prompt(job_name: str, jobs_by_name: dict[str, dict]) -> str:
    job = jobs_by_name.get(job_name)
    if job:
        message = str(job.get("payload", {}).get("message") or "").strip()
        if message:
            return message
        description = str(job.get("description") or "").strip()
        if description:
            return description
    return f'Investigate and repair cron job "{job_name}", then report the root cause and stable fix.'


def infer_channel(job_name: str, jobs_by_name: dict[str, dict]) -> str:
    job = jobs_by_name.get(job_name)
    delivery_channel = str(job.get("delivery", {}).get("channel") or "").strip() if job else ""
    return f"cron:{delivery_channel or 'unknown'}"


def record_event(args: argparse.Namespace, event: dict[str, str], jobs_by_name: dict[str, dict]) -> dict[str, object]:
    script = Path(args.repo_root) / "scripts" / "openclaw" / "agent_society_runtime_record_gap.py"
    prompt = infer_prompt(event["job_name"], jobs_by_name)
    channel = infer_channel(event["job_name"], jobs_by_name)
    observation = f'cron job "{event["job_name"]}" failed: {event["reason"]}'
    cmd = [
        sys.executable,
        str(script),
        "--root",
        str(args.root),
        "--repo-root",
        str(args.repo_root),
        "--channel",
        channel,
        "--user-id",
        event["job_name"],
        "--prompt",
        prompt,
        "--observation",
        observation,
        "--failure-status",
        "failed",
        "--next-decision",
        "classify the cron blocker and prepare a bounded repair path before the next scheduled run",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout)
    payload["job_name"] = event["job_name"]
    payload["reason"] = event["reason"]
    payload["event_key"] = event["event_key"]
    payload["channel"] = channel
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record cron failures into the agent-society self-improvement loop.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--jobs-file")
    parser.add_argument("--journal-file")
    parser.add_argument("--journal-unit", default="openclaw.service")
    parser.add_argument("--tail", type=int, default=600)
    parser.add_argument("--state-file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.root = Path(args.root)
    args.repo_root = Path(args.repo_root)
    jobs_path = Path(args.jobs_file) if args.jobs_file else None
    state_path = Path(args.state_file) if args.state_file else args.root / "cron_failure_watch_state.json"

    journal_text = load_journal_text(args)
    events = parse_failure_events(journal_text)
    jobs_by_name = load_jobs_by_name(jobs_path)
    seen = load_seen_state(state_path)

    processed: list[dict[str, object]] = []
    for event in events:
        if event["event_key"] in seen:
            continue
        payload = record_event(args, event, jobs_by_name)
        processed.append(payload)
        seen[event["event_key"]] = payload.get("gap_id", "")

    save_seen_state(state_path, seen)
    print(json.dumps({"processed": processed, "processed_count": len(processed)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
