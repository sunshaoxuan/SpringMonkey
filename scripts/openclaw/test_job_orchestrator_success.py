#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "openclaw" / "job_orchestrator.py"
    with tempfile.TemporaryDirectory(prefix="job_orchestrator_success_") as tmp:
        root = Path(tmp)
        command = root / "ok.py"
        command.write_text("print('final weather report')\n", encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--job-name",
                "weather-report-jst-0700",
                "--category",
                "weather",
                "--prompt",
                "create weather report",
                "--kernel-root",
                str(root / "kernel"),
                "--repo-root",
                str(repo_root),
                "--command",
                sys.executable,
                str(command),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        if proc.stdout.strip() != "final weather report":
            raise AssertionError(f"stdout contract changed: {proc.stdout!r}")
        sessions = list((root / "kernel" / "sessions").glob("session_*.json"))
        if len(sessions) != 1:
            raise AssertionError("expected exactly one kernel session")
        data = json.loads(sessions[0].read_text(encoding="utf-8"))
        observations = data.get("observations", [])
        if not observations or observations[-1].get("status") != "completed":
            raise AssertionError(f"expected completed observation, got {observations}")
        if not any("final weather report" in item.get("observation", "") for item in observations):
            raise AssertionError("expected stdout in observation")
        steps = data.get("steps", [])
        execute_steps = [step for step in steps if step.get("action_kind") == "tool"]
        if not execute_steps or execute_steps[0].get("context_policy") != "cron_job_isolated":
            raise AssertionError("expected cron job to use isolated context policy")
        if not any(step.get("action_kind") == "report" and step.get("status") == "completed" for step in steps):
            raise AssertionError("expected completed report step")
        print("job_orchestrator_success_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
