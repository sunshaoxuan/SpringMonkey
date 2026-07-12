#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


UTC = timezone.utc


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_json_file(path: Path | None) -> Any:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def probe_json(command: list[str], fixture: Path | None, timeout: int) -> dict[str, Any]:
    try:
        if fixture is not None:
            payload = load_json_file(fixture)
        else:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
            if proc.returncode != 0:
                return {
                    "ok": False,
                    "command": command,
                    "error": (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()[-2000:],
                }
            payload = json.loads(proc.stdout)
        return {"ok": True, "command": command, "payload": payload}
    except Exception as exc:
        return {"ok": False, "command": command, "error": f"{type(exc).__name__}: {exc}"}


def canonical_job_contract(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    delivery = job.get("delivery") if isinstance(job.get("delivery"), dict) else {}
    schedule = job.get("schedule") if isinstance(job.get("schedule"), dict) else {}
    return {
        "id": job.get("id"),
        "name": job.get("name"),
        "enabled": job.get("enabled", True),
        "schedule": schedule,
        "delivery": delivery,
        "sessionTarget": job.get("sessionTarget"),
        "sessionKey": job.get("sessionKey"),
        "payloadModel": payload.get("model"),
        "payloadFallbacks": payload.get("fallbacks"),
    }


def cron_contract(jobs_file: Path) -> dict[str, Any]:
    data = json.loads(jobs_file.read_text(encoding="utf-8"))
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    contracts = [canonical_job_contract(job) for job in jobs if isinstance(job, dict)]
    contracts.sort(key=lambda item: (str(item.get("name") or ""), str(item.get("id") or "")))
    encoded = json.dumps(contracts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "count": len(contracts),
        "fingerprint": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "jobs": contracts,
    }


def summarize_tasks(probe: dict[str, Any]) -> dict[str, Any]:
    payload = probe.get("payload") if probe.get("ok") else {}
    tasks = payload.get("tasks", []) if isinstance(payload, dict) else []
    counts: dict[str, int] = {}
    cron_failures: list[dict[str, Any]] = []
    for task in tasks if isinstance(tasks, list) else []:
        if not isinstance(task, dict):
            continue
        status = str(task.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
        if task.get("runtime") == "cron" and status in {"failed", "timed_out", "lost"}:
            cron_failures.append(
                {
                    "taskId": task.get("taskId"),
                    "sourceId": task.get("sourceId"),
                    "label": task.get("label"),
                    "status": status,
                    "error": task.get("error") or task.get("terminalSummary"),
                }
            )
    return {"count": len(tasks) if isinstance(tasks, list) else 0, "by_status": counts, "cron_failures": cron_failures}


def load_previous(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Shadow official OpenClaw runtime state without changing cron jobs or delivery.")
    parser.add_argument("--jobs-file", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--tasks-file", type=Path)
    parser.add_argument("--audit-file", type=Path)
    parser.add_argument("--doctor-file", type=Path)
    parser.add_argument("--health-file", type=Path)
    parser.add_argument("--enforce-cron-integrity", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    previous = load_previous(args.state_file)
    before = cron_contract(args.jobs_file)
    tasks = probe_json(["openclaw", "tasks", "list", "--json"], args.tasks_file, args.timeout)
    audit = probe_json(["openclaw", "tasks", "audit", "--json"], args.audit_file, args.timeout)
    doctor = probe_json(
        ["openclaw", "doctor", "--lint", "--severity-min", "warning", "--json"],
        args.doctor_file,
        args.timeout,
    )
    health = probe_json(["openclaw", "health", "--json"], args.health_file, args.timeout)
    after = cron_contract(args.jobs_file)
    previous_fingerprint = str(previous.get("cron_contract", {}).get("fingerprint") or "")
    changed_during_probe = before["fingerprint"] != after["fingerprint"]
    changed_from_previous = bool(previous_fingerprint and previous_fingerprint != after["fingerprint"])
    snapshot = {
        "schema_version": 1,
        "captured_at": utc_now(),
        "mode": "shadow",
        "mutations_performed": False,
        "delivery_performed": False,
        "cron_contract": after,
        "cron_integrity": {
            "changed_during_probe": changed_during_probe,
            "changed_from_previous_snapshot": changed_from_previous,
            "previous_fingerprint": previous_fingerprint,
        },
        "official": {
            "tasks": tasks,
            "task_summary": summarize_tasks(tasks),
            "audit": audit,
            "doctor": doctor,
            "health": health,
        },
    }
    write_json(args.state_file, snapshot)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    if args.enforce_cron_integrity and changed_during_probe:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
