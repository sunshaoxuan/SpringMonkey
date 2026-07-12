#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


FAILURE_RE = r'Cron job "(?P<job>[^"]+)" failed: (?P<reason>.+)$'
TERMINAL_FAILURE_STATUSES = {"failed", "timed_out", "lost"}


def load_official_tasks(args: argparse.Namespace) -> tuple[list[dict[str, object]], str]:
    if args.tasks_file:
        payload = json.loads(Path(args.tasks_file).read_text(encoding="utf-8"))
    else:
        result = subprocess.run(
            ["openclaw", "tasks", "list", "--runtime", "cron", "--json"],
            capture_output=True,
            text=True,
            timeout=args.tasks_timeout,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "openclaw tasks failed").strip())
        payload = json.loads(result.stdout)
    tasks = payload.get("tasks", []) if isinstance(payload, dict) else payload
    if not isinstance(tasks, list):
        raise ValueError("official tasks payload does not contain a task list")
    return [task for task in tasks if isinstance(task, dict)], "official_tasks"


def resolve_job_name(task: dict[str, object], jobs_by_name: dict[str, dict]) -> str:
    jobs_by_id = {
        str(job.get("id")): name
        for name, job in jobs_by_name.items()
        if str(job.get("id") or "").strip()
    }
    candidates = [
        str(task.get("label") or "").strip(),
        str(task.get("sourceId") or "").strip(),
        str(task.get("ownerKey") or "").strip(),
        str(task.get("task") or "").strip(),
    ]
    for candidate in candidates:
        if candidate in jobs_by_name:
            return candidate
        if candidate in jobs_by_id:
            return jobs_by_id[candidate]
        for name, job in jobs_by_name.items():
            job_id = str(job.get("id") or "").strip()
            if name and name in candidate:
                return name
            if job_id and job_id in candidate:
                return name
    return candidates[0] or candidates[1] or str(task.get("taskId") or "unknown-cron-task")


def parse_official_task_failures(
    tasks: list[dict[str, object]],
    jobs_by_name: dict[str, dict],
    *,
    max_age_seconds: int = 900,
    now_ms: int | None = None,
) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    current_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    for task in tasks:
        if str(task.get("runtime") or "") != "cron":
            continue
        status = str(task.get("status") or "")
        if status not in TERMINAL_FAILURE_STATUSES:
            continue
        ended_at = task.get("endedAt")
        if isinstance(ended_at, (int, float)) and max_age_seconds > 0:
            if current_ms - int(ended_at) > max_age_seconds * 1000:
                continue
        job_name = resolve_job_name(task, jobs_by_name)
        reason = str(
            task.get("error")
            or task.get("terminalSummary")
            or task.get("progressSummary")
            or f"official task ended with status {status}"
        ).strip()
        task_id = str(task.get("taskId") or "").strip()
        event_key = task_id or hashlib.sha1(
            f"official_tasks|{job_name}|{status}|{reason}".encode("utf-8")
        ).hexdigest()
        legacy_event_key = hashlib.sha1(f"{job_name}|{reason}".encode("utf-8")).hexdigest()
        events.append(
            {
                "job_name": job_name,
                "reason": reason,
                "event_key": event_key,
                "legacy_event_key": legacy_event_key,
                "raw_line": json.dumps(task, ensure_ascii=False, sort_keys=True),
                "source": "official_tasks",
                "task_id": task_id,
                "task_status": status,
                "delivery_status": str(task.get("deliveryStatus") or ""),
                "run_id": str(task.get("runId") or ""),
                "flow_id": str(task.get("parentFlowId") or ""),
            }
        )
    return events


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


def run_shadow_bridge(
    args: argparse.Namespace,
    jobs_path: Path | None,
) -> dict[str, object]:
    if args.disable_shadow_bridge or jobs_path is None or not jobs_path.is_file():
        return {"status": "skipped"}
    script = Path(args.repo_root) / "scripts" / "openclaw" / "official_runtime_shadow_bridge.py"
    if not script.is_file():
        return {"status": "unavailable", "reason": f"missing {script}"}
    state_file = (
        Path(args.shadow_state_file)
        if args.shadow_state_file
        else Path(args.root) / "official_runtime_shadow.json"
    )
    cmd = [
        sys.executable,
        str(script),
        "--jobs-file",
        str(jobs_path),
        "--state-file",
        str(state_file),
        "--timeout",
        str(args.tasks_timeout),
        "--enforce-cron-integrity",
    ]
    if args.tasks_file:
        cmd.extend(["--tasks-file", str(args.tasks_file)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=max(60, args.tasks_timeout * 4), check=False)
    if result.returncode != 0:
        return {
            "status": "failed",
            "returncode": result.returncode,
            "reason": (result.stderr or result.stdout or "shadow bridge failed").strip()[-2000:],
        }
    try:
        snapshot = json.loads(result.stdout)
    except Exception:
        snapshot = {}
    official = snapshot.get("official", {}) if isinstance(snapshot, dict) else {}
    return {
        "status": "captured",
        "state_file": str(state_file),
        "cron_fingerprint": str(snapshot.get("cron_contract", {}).get("fingerprint") or ""),
        "tasks_ok": bool(official.get("tasks", {}).get("ok")),
        "audit_ok": bool(official.get("audit", {}).get("ok")),
        "doctor_ok": bool(official.get("doctor", {}).get("ok")),
        "health_ok": bool(official.get("health", {}).get("ok")),
    }


def run_daily_log_retention(args: argparse.Namespace) -> dict[str, object]:
    if args.disable_log_retention:
        return {"status": "disabled"}
    if os.name == "nt" and not args.log_retention_force:
        return {"status": "skipped_non_posix"}
    script = Path(args.repo_root) / "scripts" / "openclaw" / "scheduled_log_retention.py"
    if not script.is_file():
        return {"status": "unavailable", "reason": f"missing {script}"}
    state_file = (
        Path(args.log_retention_state_file)
        if args.log_retention_state_file
        else Path(args.root) / "log_retention_run_state.json"
    )
    command = [
        sys.executable,
        str(script),
        "--repo-root",
        str(args.repo_root),
        "--state-file",
        str(state_file),
        "--archive-root",
        str(args.log_archive_root),
        "--min-free-percent",
        str(args.log_min_free_percent),
    ]
    if args.log_retention_force:
        command.append("--force")
    result = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False)
    try:
        payload = json.loads(result.stdout)
    except Exception:
        payload = {}
    if result.returncode != 0:
        return {
            "status": "failed",
            "returncode": result.returncode,
            "reason": (result.stderr or result.stdout or "scheduled log retention failed").strip()[-2000:],
        }
    return payload if isinstance(payload, dict) else {"status": "completed"}


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
    payload["signal_source"] = event.get("source", "journal")
    payload["official_task_id"] = event.get("task_id", "")
    payload["official_run_id"] = event.get("run_id", "")
    payload["official_flow_id"] = event.get("flow_id", "")
    payload["official_delivery_status"] = event.get("delivery_status", "")
    return payload


def run_recovery_guard(
    args: argparse.Namespace,
    events: list[dict[str, str]],
    tasks: list[dict[str, object]],
    jobs_by_name: dict[str, dict],
) -> dict[str, object]:
    if args.disable_recovery_guard:
        return {"status": "disabled"}
    try:
        from cron_recovery_guard import run_guard
        from official_runtime_shadow_bridge import cron_contract

        state_file = (
            Path(args.recovery_state_file)
            if args.recovery_state_file
            else Path(args.root) / "cron_recovery_guard_state.json"
        )
        before_contract = cron_contract(Path(args.jobs_file)) if args.jobs_file else {}
        result = run_guard(
            events=events,
            tasks=[task for task in tasks if isinstance(task, dict)],
            jobs_by_name=jobs_by_name,
            state_file=state_file,
            repo_root=Path(args.repo_root),
            kernel_root=Path(args.root),
            allow_restart=not args.disable_recovery_restart,
            max_reruns=args.recovery_max_reruns,
        )
        after_contract = cron_contract(Path(args.jobs_file)) if args.jobs_file else {}
        changed = bool(before_contract and after_contract and before_contract.get("fingerprint") != after_contract.get("fingerprint"))
        return {
            "status": "failed" if changed else "active",
            "cron_integrity": {
                "changed_during_recovery": changed,
                "before": before_contract.get("fingerprint", ""),
                "after": after_contract.get("fingerprint", ""),
            },
            **result,
        }
    except Exception as exc:
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record cron failures into the agent-society self-improvement loop.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--jobs-file")
    parser.add_argument("--journal-file")
    parser.add_argument("--journal-unit", default="openclaw.service")
    parser.add_argument("--tail", type=int, default=600)
    parser.add_argument("--state-file")
    parser.add_argument("--source", choices=("auto", "tasks", "journal"), default="auto")
    parser.add_argument("--tasks-file")
    parser.add_argument("--tasks-timeout", type=int, default=20)
    parser.add_argument("--official-max-age-seconds", type=int, default=900)
    parser.add_argument("--disable-shadow-bridge", action="store_true")
    parser.add_argument("--shadow-state-file")
    parser.add_argument("--disable-log-retention", action="store_true")
    parser.add_argument("--log-retention-force", action="store_true")
    parser.add_argument("--log-retention-state-file")
    parser.add_argument("--log-archive-root", default="/var/backups/openclaw-log-archive")
    parser.add_argument("--log-min-free-percent", type=float, default=10.0)
    parser.add_argument("--disable-recovery-guard", action="store_true")
    parser.add_argument("--disable-recovery-restart", action="store_true")
    parser.add_argument("--recovery-state-file")
    parser.add_argument("--recovery-max-reruns", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.root = Path(args.root)
    args.repo_root = Path(args.repo_root)
    jobs_path = Path(args.jobs_file) if args.jobs_file else None
    state_path = Path(args.state_file) if args.state_file else args.root / "cron_failure_watch_state.json"

    jobs_by_name = load_jobs_by_name(jobs_path)
    tasks: list[dict[str, object]] = []
    source = "journal"
    fallback_reason = ""
    if args.source in {"auto", "tasks"}:
        try:
            tasks, source = load_official_tasks(args)
            events = parse_official_task_failures(
                tasks,
                jobs_by_name,
                max_age_seconds=args.official_max_age_seconds,
            )
        except Exception as exc:
            if args.source == "tasks":
                raise
            fallback_reason = f"{type(exc).__name__}: {exc}"
            journal_text = load_journal_text(args)
            events = parse_failure_events(journal_text)
    else:
        journal_text = load_journal_text(args)
        events = parse_failure_events(journal_text)
    seen = load_seen_state(state_path)

    processed: list[dict[str, object]] = []
    for event in events:
        legacy_event_key = event.get("legacy_event_key", "")
        if event["event_key"] in seen or (legacy_event_key and legacy_event_key in seen):
            continue
        payload = record_event(args, event, jobs_by_name)
        processed.append(payload)
        seen[event["event_key"]] = payload.get("gap_id", "")
        if legacy_event_key:
            seen[legacy_event_key] = payload.get("gap_id", "")

    save_seen_state(state_path, seen)
    recovery_guard = run_recovery_guard(args, events, tasks, jobs_by_name)
    shadow_bridge = run_shadow_bridge(args, jobs_path)
    log_retention = run_daily_log_retention(args)
    print(
        json.dumps(
            {
                "processed": processed,
                "processed_count": len(processed),
                "signal_source": source,
                "fallback_reason": fallback_reason,
                "recovery_guard": recovery_guard,
                "shadow_bridge": shadow_bridge,
                "log_retention": log_retention,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
