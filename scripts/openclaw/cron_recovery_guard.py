#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
TERMINAL_FAILURES = {"failed", "timed_out", "lost"}
TERMINAL_SUCCESSES = {"completed", "succeeded", "success"}
TRANSIENT_TOKENS = ("timeout", "timed out", "couldn't generate", "could not generate", "temporarily", "connection reset")
MODEL_TOKENS = ("model", "agent couldn't generate", "agent could not generate", "provider", "quota", "rate limit")
CONFIG_TOKENS = ("invalid config", "config invalid", "unsupported channel", "legacy key", "schema")
AUTH_TOKENS = ("credential", "password", "login", "unauthorized", "forbidden", "api key", "token missing")
DELIVERY_TOKENS = ("delivery", "deliver", "publish", "posted")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def run_command(command: list[str], *, runner: CommandRunner, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = "/var/lib/openclaw"
    return runner(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        check=False,
    )


def command_evidence(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip()[-2000:],
        "stderr": (proc.stderr or "").strip()[-2000:],
    }


def parse_json_output(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    if proc.returncode != 0:
        return {}
    try:
        payload = json.loads(proc.stdout or "")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def health_ok(payload: dict[str, Any]) -> bool:
    if not payload:
        return False
    if payload.get("ok") is True or payload.get("status") in {"ok", "healthy", "ready"}:
        return True
    checks = payload.get("checks")
    if isinstance(checks, list) and checks:
        return all(isinstance(item, dict) and item.get("ok") is not False for item in checks)
    return False


def health_probe_ok(proc: subprocess.CompletedProcess[str]) -> bool:
    if proc.returncode != 0:
        return False
    payload = parse_json_output(proc)
    if not payload:
        return True
    if payload.get("ok") is False or str(payload.get("status") or "").lower() in {"failed", "error", "unhealthy", "down"}:
        return False
    return health_ok(payload) or proc.returncode == 0


def classify_points(event: dict[str, Any]) -> list[str]:
    reason = str(event.get("reason") or "").lower()
    points = ["cron_contract", "gateway_health", "doctor"]
    if any(token in reason for token in AUTH_TOKENS):
        points.append("credential_blocker")
    if any(token in reason for token in CONFIG_TOKENS):
        points.append("gateway_config")
    if any(token in reason for token in MODEL_TOKENS):
        points.append("model_route")
    if any(token in reason for token in DELIVERY_TOKENS) or str(event.get("delivery_status") or "").lower() == "delivered":
        points.append("delivery_integrity")
    if any(token in reason for token in TRANSIENT_TOKENS):
        points.append("transient_runtime")
    if len(points) == 3:
        points.append("capability_repair")
    return list(dict.fromkeys(points))


def find_job(jobs_by_name: dict[str, dict[str, Any]], job_name: str) -> dict[str, Any]:
    job = jobs_by_name.get(job_name)
    return job if isinstance(job, dict) else {}


def cron_run_command(job_id: str, *, euid: int | None = None) -> list[str]:
    effective_uid = os.geteuid() if euid is None and hasattr(os, "geteuid") else euid
    if effective_uid == 0:
        return ["runuser", "-u", "openclaw", "--", "env", "HOME=/var/lib/openclaw", "openclaw", "cron", "run", job_id]
    return ["openclaw", "cron", "run", job_id]


def parse_run_id(text: str) -> str:
    try:
        payload = json.loads((text or "").strip())
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("runId") or payload.get("run_id") or "")


def repair_capability_point(
    incident: dict[str, Any],
    *,
    repo_root: Path,
    kernel_root: Path,
    runner: CommandRunner,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(repo_root / "scripts" / "openclaw" / "capability_repair_runner.py"),
        "--text",
        f"Repair recurring cron job {incident['job_name']}",
        "--channel",
        f"cron:{incident['job_name']}",
        "--user-id",
        incident["job_name"],
        "--stage",
        "execute",
        "--reason",
        str(incident.get("reason") or "cron failure"),
        "--execution-output",
        str(incident.get("raw_line") or incident.get("reason") or ""),
        "--kernel-root",
        str(kernel_root),
        "--repo-root",
        str(repo_root),
        "--semantic",
        "--deploy-readonly",
    ]
    proc = run_command(command, runner=runner, timeout=900)
    payload = parse_json_output(proc)
    status = str(payload.get("status") or "failed")
    resolved = bool(payload.get("replay_allowed")) or status in {"verified", "promoted", "deployed", "replayed", "final_succeeded"}
    return {
        "status": "resolved" if resolved else ("waiting" if status == "repair_started" else "blocked"),
        "repair_status": status,
        "replay_allowed": bool(payload.get("replay_allowed")),
        "evidence": payload or command_evidence(proc),
    }


def diagnose_and_repair(
    incident: dict[str, Any],
    *,
    jobs_by_name: dict[str, dict[str, Any]],
    repo_root: Path,
    kernel_root: Path,
    runner: CommandRunner,
    allow_restart: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    job = find_job(jobs_by_name, incident["job_name"])
    for point in incident["points"]:
        if point == "cron_contract":
            job_id = str(job.get("id") or "")
            enabled = job.get("enabled") is not False
            results.append({"point": point, "status": "resolved" if job_id and enabled else "blocked", "job_id": job_id, "enabled": enabled})
            continue
        if point == "credential_blocker":
            results.append({"point": point, "status": "blocked", "reason": "credentials require owner input"})
            continue
        if point == "delivery_integrity":
            delivered = str(incident.get("delivery_status") or "").lower() == "delivered"
            results.append({"point": point, "status": "blocked" if delivered else "resolved", "delivered": delivered})
            continue
        if point == "gateway_health":
            first = run_command(["openclaw", "health", "--json"], runner=runner)
            if health_probe_ok(first):
                results.append({"point": point, "status": "resolved", "probe": command_evidence(first)})
                continue
            if not allow_restart:
                results.append({"point": point, "status": "blocked", "probe": command_evidence(first), "reason": "service restart disabled"})
                continue
            restart = run_command(["systemctl", "restart", "openclaw.service"], runner=runner)
            second = run_command(["openclaw", "health", "--json"], runner=runner)
            results.append(
                {
                    "point": point,
                    "status": "resolved" if restart.returncode == 0 and health_probe_ok(second) else "blocked",
                    "repair": command_evidence(restart),
                    "verify": command_evidence(second),
                }
            )
            continue
        if point == "doctor":
            proc = run_command(["openclaw", "doctor", "--lint", "--severity-min", "warning", "--json"], runner=runner)
            results.append({"point": point, "status": "resolved" if proc.returncode == 0 else "blocked", "probe": command_evidence(proc)})
            continue
        if point == "gateway_config":
            repair = run_command([sys.executable, str(repo_root / "scripts" / "openclaw" / "repair_legacy_gateway_config.py")], runner=runner)
            changed = "changed=true" in (repair.stdout or "").lower()
            restart = None
            if changed and allow_restart:
                restart = run_command(["systemctl", "restart", "openclaw.service"], runner=runner)
            doctor = run_command(["openclaw", "doctor", "--lint", "--severity-min", "warning", "--json"], runner=runner)
            health = run_command(["openclaw", "health", "--json"], runner=runner)
            restart_ok = restart is None or restart.returncode == 0
            results.append(
                {
                    "point": point,
                    "status": "resolved" if repair.returncode == 0 and restart_ok and doctor.returncode == 0 and health_probe_ok(health) else "blocked",
                    "repair": command_evidence(repair),
                    "restart": None if restart is None else command_evidence(restart),
                    "doctor": command_evidence(doctor),
                    "health": command_evidence(health),
                }
            )
            continue
        if point == "model_route":
            probe = run_command([sys.executable, str(repo_root / "scripts" / "openclaw" / "model_runtime_probe.py")], runner=runner)
            payload = parse_json_output(probe)
            results.append({"point": point, "status": "resolved" if probe.returncode == 0 and payload.get("status") == "ok" else "blocked", "probe": payload or command_evidence(probe)})
            continue
        if point == "transient_runtime":
            results.append({"point": point, "status": "resolved", "reason": "bounded rerun is the repair after health, doctor, and model probes"})
            continue
        if point == "capability_repair":
            result = repair_capability_point(incident, repo_root=repo_root, kernel_root=kernel_root, runner=runner)
            result["point"] = point
            results.append(result)
            continue
        results.append({"point": point, "status": "blocked", "reason": "unknown recovery point"})
    return results


def incident_key(event: dict[str, Any]) -> str:
    return str(event.get("event_key") or event.get("task_id") or f"{event.get('job_name')}:{event.get('reason')}")


def process_event(
    event: dict[str, Any],
    *,
    state: dict[str, Any],
    jobs_by_name: dict[str, dict[str, Any]],
    repo_root: Path,
    kernel_root: Path,
    runner: CommandRunner = subprocess.run,
    allow_restart: bool = True,
    max_reruns: int = 2,
    euid: int | None = None,
) -> dict[str, Any]:
    key = incident_key(event)
    incidents = state.setdefault("incidents", {})
    incident = incidents.get(key)
    if not isinstance(incident, dict):
        incident = {
            "incident_id": key,
            "job_name": str(event.get("job_name") or ""),
            "reason": str(event.get("reason") or ""),
            "raw_line": str(event.get("raw_line") or ""),
            "source_task_id": str(event.get("task_id") or ""),
            "source_run_id": str(event.get("run_id") or ""),
            "delivery_status": str(event.get("delivery_status") or ""),
            "points": classify_points(event),
            "rerun_attempts": 0,
            "status": "diagnosing",
            "created_at": utc_now(),
        }
        incidents[key] = incident
    if incident.get("status") in {"recovered", "exhausted", "blocked"}:
        return incident

    point_results = diagnose_and_repair(
        incident,
        jobs_by_name=jobs_by_name,
        repo_root=repo_root,
        kernel_root=kernel_root,
        runner=runner,
        allow_restart=allow_restart,
    )
    incident["point_results"] = point_results
    incident["updated_at"] = utc_now()
    statuses = {str(item.get("status") or "") for item in point_results}
    if "blocked" in statuses:
        incident["status"] = "blocked"
        return incident
    if "waiting" in statuses:
        incident["status"] = "waiting_repair"
        return incident
    if int(incident.get("rerun_attempts") or 0) >= max_reruns:
        incident["status"] = "exhausted"
        return incident
    job = find_job(jobs_by_name, incident["job_name"])
    job_id = str(job.get("id") or "")
    command = cron_run_command(job_id, euid=euid)
    rerun = run_command(command, runner=runner, timeout=300)
    incident["rerun_attempts"] = int(incident.get("rerun_attempts") or 0) + 1
    incident["last_rerun"] = command_evidence(rerun)
    incident["rerun_run_id"] = parse_run_id(rerun.stdout or "")
    incident["rerun_started_at"] = utc_now()
    incident["status"] = "rerun_started" if rerun.returncode == 0 else ("diagnosing" if incident["rerun_attempts"] < max_reruns else "exhausted")
    return incident


def reconcile_incidents(state: dict[str, Any], tasks: list[dict[str, Any]], *, max_reruns: int = 2) -> list[dict[str, Any]]:
    changed: list[dict[str, Any]] = []
    by_run = {str(task.get("runId") or ""): task for task in tasks if isinstance(task, dict) and task.get("runId")}
    for incident in state.get("incidents", {}).values():
        if not isinstance(incident, dict) or incident.get("status") != "rerun_started":
            continue
        run_id = str(incident.get("rerun_run_id") or "")
        task = by_run.get(run_id)
        if not task:
            continue
        status = str(task.get("status") or "")
        if status in TERMINAL_SUCCESSES:
            incident["status"] = "recovered"
            incident["recovered_at"] = utc_now()
            incident["recovery_task_id"] = str(task.get("taskId") or "")
            changed.append(incident)
        elif status in TERMINAL_FAILURES:
            incident["status"] = "diagnosing" if int(incident.get("rerun_attempts") or 0) < max_reruns else "exhausted"
            incident["last_rerun_failure"] = str(task.get("error") or task.get("terminalSummary") or status)
            changed.append(incident)
    return changed


def run_guard(
    *,
    events: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    jobs_by_name: dict[str, dict[str, Any]],
    state_file: Path,
    repo_root: Path,
    kernel_root: Path,
    runner: CommandRunner = subprocess.run,
    allow_restart: bool = True,
    max_reruns: int = 2,
    euid: int | None = None,
) -> dict[str, Any]:
    state = load_json(state_file, {"schema_version": 1, "incidents": {}})
    reconciled = reconcile_incidents(state, tasks, max_reruns=max_reruns)
    active_rerun_ids = {
        str(item.get("rerun_run_id") or "")
        for item in state.get("incidents", {}).values()
        if isinstance(item, dict) and item.get("status") in {"rerun_started", "diagnosing", "waiting_repair"}
    }
    processed: list[dict[str, Any]] = []
    for event in events:
        if str(event.get("run_id") or "") in active_rerun_ids:
            continue
        processed.append(
            process_event(
                event,
                state=state,
                jobs_by_name=jobs_by_name,
                repo_root=repo_root,
                kernel_root=kernel_root,
                runner=runner,
                allow_restart=allow_restart,
                max_reruns=max_reruns,
                euid=euid,
            )
        )
    processed_ids = {str(item.get("incident_id") or "") for item in processed}
    for incident in list(state.get("incidents", {}).values()):
        if not isinstance(incident, dict) or incident.get("status") != "diagnosing":
            continue
        incident_id = str(incident.get("incident_id") or "")
        if incident_id in processed_ids:
            continue
        processed.append(
            process_event(
                {
                    "event_key": incident_id,
                    "job_name": incident.get("job_name"),
                    "reason": incident.get("reason"),
                    "task_id": incident.get("source_task_id"),
                    "run_id": incident.get("source_run_id"),
                    "delivery_status": incident.get("delivery_status"),
                    "raw_line": incident.get("raw_line"),
                },
                state=state,
                jobs_by_name=jobs_by_name,
                repo_root=repo_root,
                kernel_root=kernel_root,
                runner=runner,
                allow_restart=allow_restart,
                max_reruns=max_reruns,
                euid=euid,
            )
        )
    state["updated_at"] = utc_now()
    write_json(state_file, state)
    return {"processed": processed, "reconciled": reconciled, "state_file": str(state_file)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose cron failure points, apply bounded repairs, and rerun the original job.")
    parser.add_argument("--events-file", type=Path, required=True)
    parser.add_argument("--tasks-file", type=Path, required=True)
    parser.add_argument("--jobs-file", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--kernel-root", type=Path, required=True)
    parser.add_argument("--max-reruns", type=int, default=2)
    parser.add_argument("--no-restart", action="store_true")
    args = parser.parse_args()
    events = load_json(args.events_file, [])
    tasks_payload = load_json(args.tasks_file, {})
    tasks = tasks_payload.get("tasks", []) if isinstance(tasks_payload, dict) else tasks_payload
    jobs_payload = load_json(args.jobs_file, {})
    jobs = jobs_payload.get("jobs", []) if isinstance(jobs_payload, dict) else []
    jobs_by_name = {str(job.get("name")): job for job in jobs if isinstance(job, dict) and job.get("name")}
    result = run_guard(
        events=[item for item in events if isinstance(item, dict)],
        tasks=[item for item in tasks if isinstance(item, dict)],
        jobs_by_name=jobs_by_name,
        state_file=args.state_file,
        repo_root=args.repo_root,
        kernel_root=args.kernel_root,
        allow_restart=not args.no_restart,
        max_reruns=args.max_reruns,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
