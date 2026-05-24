#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import long_task_supervisor
from model_fallback_client import chat_with_fallback


REPO = Path(__file__).resolve().parents[2]
DEFAULT_CAPABILITIES = REPO / "config" / "openclaw" / "recurring_job_capabilities.json"
DEFAULT_JOBS_PATH = Path("/var/lib/openclaw/.openclaw/cron/jobs.json")
DEFAULT_SESSIONS_DIR = Path("/var/lib/openclaw/.openclaw/agents/main/sessions")

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def normalize(text: str) -> str:
    return "".join((text or "").split()).lower()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def configured_jobs(path: Path = DEFAULT_CAPABILITIES) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = load_json(path)
    jobs = data.get("jobs") if isinstance(data.get("jobs"), list) else []
    return [job for job in jobs if isinstance(job, dict)]


def resolve_capability(text: str, jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
    contract = classify_recurring_capability_contract(text, jobs)
    return resolve_capability_by_id(str(contract.get("capability_id") or ""), jobs)


def extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"model did not return JSON: {raw[:160]}")
    data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("model returned non-object JSON")
    return data


def classify_recurring_capability_contract(text: str, jobs: list[dict[str, Any]], model_caller=None) -> dict[str, Any]:
    candidates = [
        {
            "capability_id": job.get("capability_id"),
            "job_name": job.get("job_name"),
            "description": job.get("description"),
            "topic_aliases": job.get("topic_aliases", []),
            "run_aliases": job.get("run_aliases", []),
        }
        for job in jobs
        if bool(job.get("allow_manual_run"))
    ]
    system = (
        "You are a semantic contract parser for an OpenClaw recurring-job executor. "
        "Choose by meaning, not keyword matching. Return strict JSON only. "
        "Schema: {supported:boolean, capability_id:string|null, confidence:number, reason:string}. "
        "Only choose a capability_id from the provided candidates. If no candidate matches, supported=false."
    )
    user = json.dumps({"user_text": text, "candidates": candidates}, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    content = model_caller(messages) if model_caller else chat_with_fallback(messages, timeout=30, temperature=0)[0]
    contract = extract_json_object(content)
    if not bool(contract.get("supported")):
        raise ValueError(str(contract.get("reason") or "no recurring capability matched"))
    capability_id = str(contract.get("capability_id") or "")
    if not any(str(item.get("capability_id") or "") == capability_id for item in candidates):
        raise ValueError(f"model selected unknown recurring capability_id: {capability_id}")
    if float(contract.get("confidence") or 0.0) < 0.65:
        raise ValueError("recurring capability contract confidence too low")
    return contract


def resolve_capability_by_id(capability_id: str, jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
    wanted = str(capability_id or "").strip()
    if not wanted:
        return None
    for job in jobs:
        if bool(job.get("allow_manual_run")) and str(job.get("capability_id") or "") == wanted:
            return dict(job)
    return None


def find_cron_job(job_name: str, jobs_payload: dict[str, Any]) -> dict[str, Any] | None:
    jobs = jobs_payload.get("jobs") if isinstance(jobs_payload.get("jobs"), list) else []
    for job in jobs:
        if isinstance(job, dict) and str(job.get("name") or "") == job_name:
            return dict(job)
    return None


def walk_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(walk_values(item))
        return values
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(walk_values(item))
        return values
    return [str(value)]


def delivery_matches(job: dict[str, Any], expected_user_id: str) -> bool:
    if not expected_user_id:
        return True
    return expected_user_id in walk_values(job)


def model_matches(job: dict[str, Any], expected_model: str) -> bool:
    if not expected_model:
        return True
    return expected_model in walk_values(job)


def validate_job(capability: dict[str, Any], cron_job: dict[str, Any]) -> tuple[bool, str]:
    if cron_job.get("enabled") is False:
        return False, "cron job is disabled"
    expected_model = str(capability.get("expected_model") or "")
    if not model_matches(cron_job, expected_model):
        return False, f"cron job model does not match expected model: {expected_model}"
    expected_channel_id = str(capability.get("expected_delivery_channel_id") or "")
    if expected_channel_id and str(cron_job.get("delivery", {}).get("to") or "") != expected_channel_id:
        return False, f"cron job delivery does not match expected channel id: {expected_channel_id}"
    expected_user_id = str(capability.get("expected_delivery_user_id") or "")
    if not delivery_matches(cron_job, expected_user_id):
        return False, f"cron job delivery does not include expected owner id: {expected_user_id}"
    return True, "ok"


def cron_run_command(job_id: str) -> list[str]:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return ["runuser", "-u", "openclaw", "--", "env", "HOME=/var/lib/openclaw", "openclaw", "cron", "run", job_id]
    env_home = os.environ.get("HOME")
    if not env_home:
        os.environ["HOME"] = "/var/lib/openclaw"
    return ["openclaw", "cron", "run", job_id]


def diagnostic_lines(stderr: str) -> list[str]:
    return [line.strip() for line in (stderr or "").splitlines() if line.strip()]


def success_payload(
    *,
    capability: dict[str, Any],
    job_name: str,
    job_id: str,
    returncode: int,
    stdout: str,
    stderr: str,
) -> dict[str, Any]:
    lines = diagnostic_lines(stderr)
    payload: dict[str, Any] = {
        "status": "success",
        "capability_id": capability.get("capability_id"),
        "job_name": job_name,
        "job_id": job_id,
        "returncode": returncode,
        "summary": "configured recurring job was triggered",
        "diagnostics": {
            "stderr_line_count": len(lines),
            "stderr_hidden": bool(lines),
        },
    }
    clean_stdout = (stdout or "").strip()
    if clean_stdout:
        payload["stdout"] = clean_stdout[-1200:]
    return payload


def parse_cron_run_id(stdout: str) -> str:
    raw = (stdout or "").strip()
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    return str(payload.get("runId") or payload.get("run_id") or "")


def failure_payload(
    *,
    capability: dict[str, Any],
    job_name: str,
    job_id: str,
    returncode: int,
    stdout: str,
    stderr: str,
) -> dict[str, Any]:
    return {
        "status": "failed",
        "capability_id": capability.get("capability_id"),
        "job_name": job_name,
        "job_id": job_id,
        "returncode": returncode,
        "stdout": (stdout or "").strip()[-2000:],
        "stderr": (stderr or "").strip()[-2000:],
    }


def message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and str(item.get("text") or "").strip():
            parts.append(str(item.get("text") or "").strip())
    return "\n".join(parts).strip()


def is_final_answer(message: dict[str, Any]) -> bool:
    if message.get("role") != "assistant":
        return False
    content = message.get("content")
    if not isinstance(content, list):
        return bool(message_text(message))
    for item in content:
        if not isinstance(item, dict):
            continue
        signature = item.get("textSignature")
        if isinstance(signature, str) and '"phase":"final_answer"' in signature:
            return True
    return False


def parse_session_final_answer(path: Path) -> str:
    final = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = row.get("message") if isinstance(row.get("message"), dict) else {}
        if is_final_answer(message):
            text = message_text(message)
            if text:
                final = text
    return final


def latest_cron_session(job_id: str, sessions_dir: Path = DEFAULT_SESSIONS_DIR, *, started_at: float = 0.0) -> Path | None:
    if not sessions_dir.is_dir():
        return None
    candidates: list[Path] = []
    needle = f"cron:{job_id}:run"
    for path in sessions_dir.glob("*.jsonl"):
        try:
            stat = path.stat()
        except OSError:
            continue
        if started_at and stat.st_mtime + 2 < started_at:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if needle in text or job_id in text:
            candidates.append(path)
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            1 if item.name.endswith(".jsonl") and ".trajectory." not in item.name else 0,
            item.stat().st_mtime,
        ),
        reverse=True,
    )
    return candidates[0]


def cron_final_report(job_id: str, *, started_at: float, sessions_dir: Path = DEFAULT_SESSIONS_DIR) -> dict[str, Any]:
    session = latest_cron_session(job_id, sessions_dir, started_at=started_at)
    if not session:
        return {"found": False, "reason": "no matching cron session found"}
    final = parse_session_final_answer(session)
    if not final:
        return {"found": False, "session_file": str(session), "reason": "matching session has no final answer"}
    return {"found": True, "session_file": str(session), "text": final}


def run_capability(
    *,
    text: str,
    capabilities_path: Path,
    jobs_path: Path,
    dry_run: bool,
    timeout: int,
    supervisor_state: Path = long_task_supervisor.DEFAULT_STATE_PATH,
    sessions_dir: Path = DEFAULT_SESSIONS_DIR,
    reply_channel_id: str = "",
    capability_id: str = "",
    model_caller=None,
) -> tuple[int, dict[str, Any]]:
    configured = configured_jobs(capabilities_path)
    capability = resolve_capability_by_id(capability_id, configured)
    if not capability:
        try:
            contract = classify_recurring_capability_contract(text, configured, model_caller=model_caller)
            capability = resolve_capability_by_id(str(contract.get("capability_id") or ""), configured)
        except Exception:
            capability = None
    if not capability:
        return 2, {"status": "error", "error": "no configured recurring job capability matched the request"}
    job_name = str(capability.get("job_name") or "")
    if not job_name:
        return 2, {"status": "error", "error": "matched capability has no job_name", "capability_id": capability.get("capability_id")}
    if not jobs_path.is_file():
        return 2, {"status": "error", "error": f"cron jobs file not found: {jobs_path}", "job_name": job_name}
    cron_job = find_cron_job(job_name, load_json(jobs_path))
    if not cron_job:
        return 2, {"status": "error", "error": "configured cron job is not present in runtime jobs.json", "job_name": job_name}
    ok, reason = validate_job(capability, cron_job)
    if not ok:
        return 2, {"status": "error", "error": reason, "job_name": job_name, "job_id": cron_job.get("id")}
    job_id = str(cron_job.get("id") or "")
    if not job_id:
        return 2, {"status": "error", "error": "cron job has no id", "job_name": job_name}
    command = cron_run_command(job_id)
    if dry_run:
        return 0, {
            "status": "dry_run",
            "capability_id": capability.get("capability_id"),
            "job_name": job_name,
            "job_id": job_id,
            "command": command,
        }
    started_at = time.time()
    proc = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if proc.returncode == 0:
        run_id = parse_cron_run_id(proc.stdout or "")
        payload = success_payload(
            capability=capability,
            job_name=job_name,
            job_id=job_id,
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )
        report = cron_final_report(job_id, started_at=started_at, sessions_dir=sessions_dir)
        if report.get("found"):
            payload["final_report"] = report.get("text")
            payload["session_file"] = report.get("session_file")
            payload["status"] = "success"
        else:
            if run_id:
                task = long_task_supervisor.register_task(
                    source="cron",
                    job_id=job_id,
                    run_id=run_id,
                    job_name=job_name,
                    reply_target="owner_dm",
                    reply_channel_id=reply_channel_id,
                    original_text=text,
                    timeout_seconds=timeout,
                    state_path=supervisor_state,
                )
                payload["long_task_id"] = task.get("task_id")
                payload["run_id"] = run_id
            payload["final_report_status"] = report
            payload["status"] = "running"
            payload["summary"] = "configured recurring job was triggered and is being tracked"
        return proc.returncode, payload
    return proc.returncode, failure_payload(
        capability=capability,
        job_name=job_name,
        job_id=job_id,
        returncode=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a configured recurring OpenClaw cron job from an owner DM request.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--message-timestamp", default="")
    parser.add_argument("--capabilities", type=Path, default=DEFAULT_CAPABILITIES)
    parser.add_argument("--jobs-path", type=Path, default=Path(os.environ.get("OPENCLAW_CRON_JOBS_PATH", str(DEFAULT_JOBS_PATH))))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--supervisor-state", type=Path, default=long_task_supervisor.DEFAULT_STATE_PATH)
    parser.add_argument("--sessions-dir", type=Path, default=DEFAULT_SESSIONS_DIR)
    parser.add_argument("--reply-channel-id", default="")
    parser.add_argument("--capability-id", default="")
    args = parser.parse_args()
    code, payload = run_capability(
        text=args.text,
        capabilities_path=args.capabilities,
        jobs_path=args.jobs_path,
        dry_run=args.dry_run,
        timeout=args.timeout,
        supervisor_state=args.supervisor_state,
        sessions_dir=args.sessions_dir,
        reply_channel_id=args.reply_channel_id,
        capability_id=args.capability_id,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
