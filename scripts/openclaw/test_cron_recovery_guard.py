from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cron_recovery_guard import process_event, reconcile_incidents, run_guard


class FakeRunner:
    def __init__(self, responses: list[tuple[int, str, str]]) -> None:
        self.responses = list(responses)
        self.commands: list[list[str]] = []

    def __call__(self, command, **_kwargs):
        self.commands.append(list(command))
        code, stdout, stderr = self.responses.pop(0)
        return subprocess.CompletedProcess(command, code, stdout=stdout, stderr=stderr)


def job() -> dict:
    return {"id": "job-1", "name": "daily-job", "enabled": True, "delivery": {"to": "owner"}}


def event(reason: str = "Agent couldn't generate a response") -> dict:
    return {
        "event_key": "failure-1",
        "job_name": "daily-job",
        "reason": reason,
        "task_id": "task-1",
        "run_id": "run-1",
        "delivery_status": "failed",
        "raw_line": reason,
    }


def test_model_failure_probes_points_then_reruns_original_job(tmp_path: Path) -> None:
    runner = FakeRunner(
        [
            (0, json.dumps({"status": "healthy"}), ""),
            (0, json.dumps({"warnings": []}), ""),
            (0, json.dumps({"kind": "text", "status": "ok", "models": [{"model_ref": "openai/gpt"}]}), ""),
            (0, json.dumps({"runId": "rerun-1"}), ""),
        ]
    )
    state = {"schema_version": 1, "incidents": {}}

    incident = process_event(
        event(),
        state=state,
        jobs_by_name={"daily-job": job()},
        repo_root=tmp_path,
        kernel_root=tmp_path / "kernel",
        runner=runner,
        euid=1000,
    )

    assert incident["status"] == "rerun_started"
    assert incident["rerun_run_id"] == "rerun-1"
    assert [item["point"] for item in incident["point_results"]] == [
        "cron_contract",
        "gateway_health",
        "doctor",
        "model_route",
        "transient_runtime",
    ]
    assert runner.commands[-1] == ["openclaw", "cron", "run", "job-1"]


def test_unhealthy_gateway_is_restarted_and_verified_before_rerun(tmp_path: Path) -> None:
    runner = FakeRunner(
        [
            (1, "", "down"),
            (0, "", ""),
            (0, json.dumps({"ok": True}), ""),
            (0, json.dumps({}), ""),
            (0, json.dumps({"runId": "rerun-2"}), ""),
        ]
    )
    state = {"schema_version": 1, "incidents": {}}

    incident = process_event(
        event("cron execution timed out"),
        state=state,
        jobs_by_name={"daily-job": job()},
        repo_root=tmp_path,
        kernel_root=tmp_path / "kernel",
        runner=runner,
        euid=0,
    )

    assert incident["status"] == "rerun_started"
    assert ["systemctl", "restart", "openclaw.service"] in runner.commands
    assert runner.commands[-1][-4:] == ["openclaw", "cron", "run", "job-1"]


def test_credentials_block_rerun(tmp_path: Path) -> None:
    runner = FakeRunner(
        [
            (0, json.dumps({"ok": True}), ""),
            (0, json.dumps({}), ""),
        ]
    )
    state = {"schema_version": 1, "incidents": {}}

    incident = process_event(
        event("login credential missing"),
        state=state,
        jobs_by_name={"daily-job": job()},
        repo_root=tmp_path,
        kernel_root=tmp_path / "kernel",
        runner=runner,
        euid=1000,
    )

    assert incident["status"] == "blocked"
    assert not any(command[:3] == ["openclaw", "cron", "run"] for command in runner.commands)


def test_config_repair_restarts_gateway_and_rechecks_doctor_and_health(tmp_path: Path) -> None:
    runner = FakeRunner(
        [
            (0, json.dumps({"ok": True}), ""),
            (0, json.dumps({}), ""),
            (0, "openclaw.json: changed=true actions=removed legacy key", ""),
            (0, "", ""),
            (0, json.dumps({"warnings": []}), ""),
            (0, json.dumps({"status": "healthy"}), ""),
            (0, json.dumps({"runId": "rerun-config"}), ""),
        ]
    )
    state = {"schema_version": 1, "incidents": {}}

    incident = process_event(
        event("Invalid config legacy key"),
        state=state,
        jobs_by_name={"daily-job": job()},
        repo_root=tmp_path,
        kernel_root=tmp_path / "kernel",
        runner=runner,
        euid=1000,
    )

    assert incident["status"] == "rerun_started"
    assert runner.commands.count(["systemctl", "restart", "openclaw.service"]) == 1
    config_point = next(item for item in incident["point_results"] if item["point"] == "gateway_config")
    assert config_point["status"] == "resolved"
    assert config_point["health"]["returncode"] == 0


def test_successful_rerun_closes_incident() -> None:
    state = {
        "incidents": {
            "failure-1": {
                "status": "rerun_started",
                "rerun_run_id": "rerun-1",
                "rerun_attempts": 1,
            }
        }
    }

    changed = reconcile_incidents(
        state,
        [{"taskId": "task-2", "runId": "rerun-1", "status": "succeeded"}],
    )

    assert len(changed) == 1
    assert state["incidents"]["failure-1"]["status"] == "recovered"


def test_guard_persists_incident_state(tmp_path: Path) -> None:
    runner = FakeRunner(
        [
            (0, json.dumps({"ok": True}), ""),
            (0, json.dumps({}), ""),
            (0, json.dumps({"kind": "text", "status": "ok", "models": [{}]}), ""),
            (0, json.dumps({"runId": "rerun-persisted"}), ""),
        ]
    )
    state_file = tmp_path / "recovery.json"

    result = run_guard(
        events=[event()],
        tasks=[],
        jobs_by_name={"daily-job": job()},
        state_file=state_file,
        repo_root=tmp_path,
        kernel_root=tmp_path / "kernel",
        runner=runner,
        euid=1000,
    )

    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert result["processed"][0]["status"] == "rerun_started"
    assert saved["incidents"]["failure-1"]["rerun_run_id"] == "rerun-persisted"


def test_failed_rerun_is_repaired_and_driven_to_second_attempt(tmp_path: Path) -> None:
    state_file = tmp_path / "recovery.json"
    state_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "incidents": {
                    "failure-1": {
                        "incident_id": "failure-1",
                        "job_name": "daily-job",
                        "reason": "cron execution timed out",
                        "raw_line": "timeout",
                        "source_task_id": "task-1",
                        "source_run_id": "run-1",
                        "delivery_status": "failed",
                        "points": ["cron_contract", "gateway_health", "doctor", "transient_runtime"],
                        "rerun_attempts": 1,
                        "rerun_run_id": "rerun-failed",
                        "status": "rerun_started",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    runner = FakeRunner(
        [
            (0, json.dumps({"ok": True}), ""),
            (0, json.dumps({}), ""),
            (0, json.dumps({"runId": "rerun-second"}), ""),
        ]
    )

    result = run_guard(
        events=[],
        tasks=[{"taskId": "task-rerun", "runId": "rerun-failed", "status": "failed", "error": "still timed out"}],
        jobs_by_name={"daily-job": job()},
        state_file=state_file,
        repo_root=tmp_path,
        kernel_root=tmp_path / "kernel",
        runner=runner,
        euid=1000,
    )

    assert result["processed"][0]["status"] == "rerun_started"
    assert result["processed"][0]["rerun_attempts"] == 2
    assert result["processed"][0]["rerun_run_id"] == "rerun-second"
