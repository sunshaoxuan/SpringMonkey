from __future__ import annotations

import json
import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from cron_failure_self_heal import load_official_cron_jobs, parse_official_task_failures
from official_runtime_shadow_bridge import cron_contract, cron_contract_from_jobs


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_shadow_bridge_uses_official_surfaces_without_changing_cron(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    jobs = tmp_path / "jobs.json"
    state = tmp_path / "shadow.json"
    tasks = tmp_path / "tasks.json"
    audit = tmp_path / "audit.json"
    doctor = tmp_path / "doctor.json"
    health = tmp_path / "health.json"
    jobs_payload = {
        "jobs": [
            {
                "id": "job-1",
                "name": "timescar-book-sat",
                "enabled": True,
                "schedule": {"expr": "0 7 * * 6", "tz": "Asia/Tokyo"},
                "delivery": {"channel": "discord", "to": "1497009159940608020"},
                "payload": {"model": "openai-codex/gpt-5.6"},
                "sessionTarget": "isolated",
            }
        ]
    }
    write_json(jobs, jobs_payload)
    original = jobs.read_bytes()
    write_json(
        tasks,
        {
            "count": 1,
            "tasks": [
                {
                    "taskId": "task-1",
                    "runtime": "cron",
                    "sourceId": "job-1",
                    "label": "timescar-book-sat",
                    "status": "failed",
                    "error": "fixture failure",
                }
            ],
        },
    )
    write_json(audit, {"findings": []})
    write_json(doctor, {"ok": True, "checksRun": 4, "findings": []})
    write_json(health, {"ok": True, "channels": {"discord": {"ok": True}}})
    proc = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "openclaw" / "official_runtime_shadow_bridge.py"),
            "--jobs-file",
            str(jobs),
            "--state-file",
            str(state),
            "--tasks-file",
            str(tasks),
            "--audit-file",
            str(audit),
            "--doctor-file",
            str(doctor),
            "--health-file",
            str(health),
            "--enforce-cron-integrity",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["mode"] == "shadow"
    assert payload["mutations_performed"] is False
    assert payload["delivery_performed"] is False
    assert payload["cron_contract"]["count"] == 1
    assert payload["cron_integrity"]["changed_during_probe"] is False
    assert payload["official"]["task_summary"]["cron_failures"][0]["taskId"] == "task-1"
    assert jobs.read_bytes() == original


def test_migration_config_forbids_public_test_delivery() -> None:
    repo = Path(__file__).resolve().parents[2]
    cfg = json.loads((repo / "config" / "openclaw" / "official_runtime_migration.json").read_text(encoding="utf-8"))
    assert cfg["mode"] == "shadow"
    assert cfg["preserve_existing_cron_jobs"] is True
    assert cfg["preserve_existing_timers"] is True
    assert cfg["test_delivery_policy"] == "owner_dm_only"
    assert cfg["public_test_delivery_forbidden"] is True
    assert cfg["recovery_guard"]["enabled"] is True
    assert cfg["recovery_guard"]["mode"] == "official_first_extension"
    assert cfg["recovery_guard"]["max_reruns_per_incident"] == 2
    assert cfg["recovery_guard"]["official_retry_attempts"] == 3
    assert cfg["recovery_guard"]["official_recurring_backoff_tiers"] == 5
    assert cfg["recovery_guard"]["run_official_doctor_fix_before_custom_repair"] is True
    assert cfg["recovery_guard"]["preserve_cron_contract"] is True
    assert set(cfg["owner_discord_dm_channel_ids"]).isdisjoint(cfg["public_discord_channel_ids"])


def test_official_job_list_contract_matches_file_contract(tmp_path: Path) -> None:
    jobs = [
        {
            "id": "job-1",
            "name": "daily",
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 7 * * *"},
            "delivery": {"channel": "discord", "to": "owner"},
            "payload": {"model": "openai/gpt", "fallbacks": ["ollama/qwen"]},
        }
    ]
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")

    assert cron_contract_from_jobs(jobs)["fingerprint"] == cron_contract(jobs_file)["fingerprint"]


def test_official_cron_catalog_is_loaded_from_cli_fixture(tmp_path: Path) -> None:
    cron_list = tmp_path / "cron-list.json"
    cron_list.write_text(
        json.dumps({"jobs": [{"id": "job-1", "name": "daily", "status": "error", "state": {"consecutiveErrors": 5}}]}),
        encoding="utf-8",
    )

    jobs, source = load_official_cron_jobs(argparse.Namespace(cron_list_file=str(cron_list), tasks_timeout=1))

    assert source == "official_cron_list"
    assert jobs["daily"]["state"]["consecutiveErrors"] == 5


def test_official_task_parser_ignores_retained_historical_failures() -> None:
    tasks = [
        {
            "taskId": "old-task",
            "runtime": "cron",
            "label": "daily-job",
            "status": "failed",
            "error": "old failure",
            "endedAt": 1_000,
        },
        {
            "taskId": "new-task",
            "runtime": "cron",
            "label": "daily-job",
            "status": "failed",
            "error": "new failure",
            "endedAt": 900_000,
        },
    ]
    events = parse_official_task_failures(
        tasks,
        {"daily-job": {"name": "daily-job"}},
        max_age_seconds=200,
        now_ms=1_000_000,
    )
    assert [event["event_key"] for event in events] == ["new-task"]
