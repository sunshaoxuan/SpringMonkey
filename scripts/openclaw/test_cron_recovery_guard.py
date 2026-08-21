from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cron_recovery_guard import newest_failure_events, official_handoff_decision, process_event, reconcile_incidents, refresh_official_handoff, run_guard


class FakeRunner:
    def __init__(self, responses: list[tuple[int, str, str]]) -> None:
        self.responses = list(responses)
        self.commands: list[list[str]] = []

    def __call__(self, command, **_kwargs):
        self.commands.append(list(command))
        code, stdout, stderr = self.responses.pop(0)
        return subprocess.CompletedProcess(command, code, stdout=stdout, stderr=stderr)


def job() -> dict:
    return {
        "id": "job-1",
        "name": "daily-job",
        "enabled": True,
        "status": "error",
        "schedule": {"kind": "cron", "expr": "0 7 * * *"},
        "state": {"lastRunStatus": "error", "consecutiveErrors": 5, "nextRunAtMs": 4102444800000},
        "delivery": {"to": "owner"},
    }


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
        refresh_official_before_rerun=False,
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
            (0, "official repair completed", ""),
            (1, "", "still down"),
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
        refresh_official_before_rerun=False,
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


def test_official_recurring_backoff_owns_failure_before_saturation() -> None:
    official_job = job()
    official_job["state"]["consecutiveErrors"] = 2
    decision = official_handoff_decision(
        {"job_name": "daily-job", "reason": "request timed out", "first_seen_at_ms": 1, "task_status": "failed"},
        job=official_job,
        tasks=[],
        now_ms=1000,
        official_retry_attempts=3,
        official_backoff_tiers=5,
        official_next_run_guard_ms=300_000,
        unknown_state_handoff_ms=3_600_000,
    )
    assert decision["handoff"] is False
    assert decision["reason"] == "official_recurring_backoff_not_saturated"


def test_official_active_run_blocks_custom_rerun() -> None:
    decision = official_handoff_decision(
        {"job_name": "daily-job", "reason": "permanent failure", "first_seen_at_ms": 1, "task_status": "failed"},
        job=job(),
        tasks=[{"taskId": "active", "status": "running", "sourceId": "daily-job"}],
        now_ms=1000,
        official_retry_attempts=3,
        official_backoff_tiers=5,
        official_next_run_guard_ms=300_000,
        unknown_state_handoff_ms=3_600_000,
    )
    assert decision["handoff"] is False
    assert decision["reason"] == "official_run_in_flight"


def test_one_shot_waits_for_official_retry_slot() -> None:
    official_job = job()
    official_job["schedule"] = {"kind": "at", "at": "2026-07-12T12:00:00Z"}
    official_job["state"] = {"lastRunStatus": "error", "consecutiveErrors": 1, "nextRunAtMs": 2000}
    decision = official_handoff_decision(
        {"job_name": "daily-job", "reason": "network timeout", "first_seen_at_ms": 1, "task_status": "failed"},
        job=official_job,
        tasks=[],
        now_ms=1000,
        official_retry_attempts=3,
        official_backoff_tiers=5,
        official_next_run_guard_ms=300_000,
        unknown_state_handoff_ms=3_600_000,
    )
    assert decision["handoff"] is False
    assert decision["reason"] == "official_one_shot_retry_pending"


def test_waiting_official_does_not_probe_or_rerun(tmp_path: Path) -> None:
    official_job = job()
    official_job["state"]["consecutiveErrors"] = 1
    runner = FakeRunner([])
    state = {"schema_version": 1, "incidents": {}}

    incident = process_event(
        event("cron execution timed out"),
        state=state,
        jobs_by_name={"daily-job": official_job},
        repo_root=tmp_path,
        kernel_root=tmp_path / "kernel",
        runner=runner,
        euid=1000,
    )

    assert incident["status"] == "waiting_official"
    assert incident["official_handoff"]["reason"] == "official_recurring_backoff_not_saturated"
    assert runner.commands == []


def test_pre_rerun_refresh_blocks_when_official_run_started() -> None:
    runner = FakeRunner(
        [
            (0, json.dumps(job()), ""),
            (0, json.dumps({"tasks": [{"taskId": "official-active", "status": "running", "sourceId": "daily-job"}]}), ""),
        ]
    )

    decision = refresh_official_handoff(
        {"job_name": "daily-job", "reason": "permanent failure", "first_seen_at_ms": 1, "task_status": "failed"},
        job_id="job-1",
        runner=runner,
        official_retry_attempts=3,
        official_backoff_tiers=5,
        official_next_run_guard_ms=300_000,
        unknown_state_handoff_ms=3_600_000,
    )

    assert decision["handoff"] is False
    assert decision["reason"] == "official_run_in_flight"


def test_official_retry_failures_collapse_to_latest_event_per_job() -> None:
    events = [
        {**event("first failure"), "task_id": "task-1", "run_id": "run-1", "ended_at": "100"},
        {**event("second failure"), "task_id": "task-2", "run_id": "run-2", "ended_at": "200"},
        {**event("other job"), "job_name": "other-job", "task_id": "task-3", "run_id": "run-3", "ended_at": "150"},
    ]

    collapsed = newest_failure_events(events)

    assert len(collapsed) == 2
    latest_daily = next(item for item in collapsed if item["job_name"] == "daily-job")
    assert latest_daily["run_id"] == "run-2"


def test_terminal_incident_starts_new_generation_for_new_official_run(tmp_path: Path) -> None:
    state = {
        "incidents": {
            "cron-job:daily-job": {
                "incident_id": "cron-job:daily-job",
                "job_name": "daily-job",
                "source_run_id": "old-run",
                "status": "recovered",
                "updated_at": "2026-07-12T00:00:00+00:00",
            }
        }
    }
    official_job = job()
    official_job["state"]["consecutiveErrors"] = 1
    runner = FakeRunner([])

    incident = process_event(
        {**event("new timeout"), "run_id": "new-run"},
        state=state,
        jobs_by_name={"daily-job": official_job},
        repo_root=tmp_path,
        kernel_root=tmp_path / "kernel",
        runner=runner,
        euid=1000,
    )

    assert incident["status"] == "waiting_official"
    assert incident["source_run_id"] == "new-run"
    assert incident["previous_incident"]["status"] == "recovered"


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
        refresh_official_before_rerun=False,
    )

    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert result["processed"][0]["status"] == "rerun_started"
    assert saved["incidents"]["cron-job:daily-job"]["rerun_run_id"] == "rerun-persisted"


def test_failed_rerun_is_repaired_and_driven_to_second_attempt(tmp_path: Path) -> None:
    state_file = tmp_path / "recovery.json"
    state_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "incidents": {
                    "cron-job:daily-job": {
                        "incident_id": "cron-job:daily-job",
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
        refresh_official_before_rerun=False,
    )

    assert result["processed"][0]["status"] == "rerun_started"
    assert result["processed"][0]["rerun_attempts"] == 2
    assert result["processed"][0]["rerun_run_id"] == "rerun-second"
