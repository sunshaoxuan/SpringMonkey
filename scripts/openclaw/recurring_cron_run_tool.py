#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
DEFAULT_CAPABILITIES = REPO / "config" / "openclaw" / "recurring_job_capabilities.json"
DEFAULT_JOBS_PATH = Path("/var/lib/openclaw/.openclaw/cron/jobs.json")

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
    raw = normalize(text)
    best: tuple[int, dict[str, Any]] | None = None
    for job in jobs:
        if not bool(job.get("allow_manual_run")):
            continue
        topic_hits = [alias for alias in job.get("topic_aliases", []) if normalize(str(alias)) in raw]
        run_hits = [alias for alias in job.get("run_aliases", []) if normalize(str(alias)) in raw]
        if not topic_hits or not run_hits:
            continue
        score = len(topic_hits) * 10 + len(run_hits)
        if best is None or score > best[0]:
            best = (score, job)
    return None if best is None else dict(best[1])


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


def run_capability(
    *,
    text: str,
    capabilities_path: Path,
    jobs_path: Path,
    dry_run: bool,
    timeout: int,
) -> tuple[int, dict[str, Any]]:
    capability = resolve_capability(text, configured_jobs(capabilities_path))
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
    proc = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    return proc.returncode, {
        "status": "success" if proc.returncode == 0 else "failed",
        "capability_id": capability.get("capability_id"),
        "job_name": job_name,
        "job_id": job_id,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip()[-2000:],
        "stderr": (proc.stderr or "").strip()[-2000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a configured recurring OpenClaw cron job from an owner DM request.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--message-timestamp", default="")
    parser.add_argument("--capabilities", type=Path, default=DEFAULT_CAPABILITIES)
    parser.add_argument("--jobs-path", type=Path, default=Path(os.environ.get("OPENCLAW_CRON_JOBS_PATH", str(DEFAULT_JOBS_PATH))))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()
    code, payload = run_capability(
        text=args.text,
        capabilities_path=args.capabilities,
        jobs_path=args.jobs_path,
        dry_run=args.dry_run,
        timeout=args.timeout,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
