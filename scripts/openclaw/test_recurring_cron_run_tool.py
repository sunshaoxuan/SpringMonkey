from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import recurring_cron_run_tool as tool


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_recurring_cron_run_resolves_configured_job_and_dry_runs(tmp_path: Path) -> None:
    capabilities = tmp_path / "capabilities.json"
    jobs = tmp_path / "jobs.json"
    write_json(
        capabilities,
        {
            "schema_version": 1,
            "jobs": [
                {
                    "capability_id": "recurring.test",
                    "job_name": "content-job",
                    "topic_aliases": ["内容任务"],
                    "run_aliases": ["开始执行"],
                    "allow_manual_run": True,
                    "expected_model": "openai-codex/gpt-5.5",
                    "expected_delivery_user_id": "owner-1",
                }
            ],
        },
    )
    write_json(
        jobs,
        {
            "jobs": [
                {
                    "id": "job_1",
                    "name": "content-job",
                    "enabled": True,
                    "payload": {"model": "openai-codex/gpt-5.5"},
                    "delivery": {"userId": "owner-1"},
                }
            ]
        },
    )

    code, payload = tool.run_capability(
        text="请开始执行内容任务",
        capabilities_path=capabilities,
        jobs_path=jobs,
        dry_run=True,
        timeout=10,
    )

    assert code == 0
    assert payload["status"] == "dry_run"
    assert payload["job_name"] == "content-job"
    assert payload["job_id"] == "job_1"


def test_recurring_cron_run_rejects_unconfigured_topic(tmp_path: Path) -> None:
    capabilities = tmp_path / "capabilities.json"
    jobs = tmp_path / "jobs.json"
    write_json(capabilities, {"schema_version": 1, "jobs": []})
    write_json(jobs, {"jobs": []})

    code, payload = tool.run_capability(
        text="请开始执行不存在的任务",
        capabilities_path=capabilities,
        jobs_path=jobs,
        dry_run=True,
        timeout=10,
    )

    assert code == 2
    assert payload["status"] == "error"


def test_recurring_cron_run_rejects_model_drift(tmp_path: Path) -> None:
    capabilities = tmp_path / "capabilities.json"
    jobs = tmp_path / "jobs.json"
    write_json(
        capabilities,
        {
            "schema_version": 1,
            "jobs": [
                {
                    "capability_id": "recurring.test",
                    "job_name": "content-job",
                    "topic_aliases": ["内容任务"],
                    "run_aliases": ["执行"],
                    "allow_manual_run": True,
                    "expected_model": "openai-codex/gpt-5.5",
                }
            ],
        },
    )
    write_json(
        jobs,
        {"jobs": [{"id": "job_1", "name": "content-job", "enabled": True, "payload": {"model": "default"}}]},
    )

    code, payload = tool.run_capability(
        text="执行内容任务",
        capabilities_path=capabilities,
        jobs_path=jobs,
        dry_run=True,
        timeout=10,
    )

    assert code == 2
    assert "model" in payload["error"]


def test_success_payload_hides_stderr_noise() -> None:
    payload = tool.success_payload(
        capability={"capability_id": "recurring.test"},
        job_name="content-job",
        job_id="job_1",
        returncode=0,
        stdout="started\n",
        stderr="plugin not installed: line\nplugin not installed: whatsapp\n",
    )

    assert payload["status"] == "success"
    assert "stderr" not in payload
    assert payload["diagnostics"]["stderr_line_count"] == 2
    assert payload["diagnostics"]["stderr_hidden"] is True


def test_failed_run_keeps_stderr_tail(tmp_path: Path) -> None:
    capabilities = tmp_path / "capabilities.json"
    jobs = tmp_path / "jobs.json"
    write_json(
        capabilities,
        {
            "schema_version": 1,
            "jobs": [
                {
                    "capability_id": "recurring.test",
                    "job_name": "content-job",
                    "topic_aliases": ["内容任务"],
                    "run_aliases": ["执行"],
                    "allow_manual_run": True,
                }
            ],
        },
    )
    write_json(jobs, {"jobs": [{"id": "job_1", "name": "content-job", "enabled": True}]})
    completed = SimpleNamespace(returncode=7, stdout="", stderr="real failure")

    with patch.object(tool.subprocess, "run", return_value=completed):
        code, payload = tool.run_capability(
            text="执行内容任务",
            capabilities_path=capabilities,
            jobs_path=jobs,
            dry_run=False,
            timeout=10,
        )

    assert code == 7
    assert payload["status"] == "failed"
    assert payload["stderr"] == "real failure"


def test_parse_session_final_answer_extracts_final_text(tmp_path: Path) -> None:
    session = tmp_path / "session.jsonl"
    session.write_text(
        "\n".join(
            [
                json.dumps({"message": {"role": "assistant", "content": [{"type": "text", "text": "progress"}]}}),
                json.dumps(
                    {
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "已完成。\nhttps://docs.example/doc",
                                    "textSignature": '{"phase":"final_answer"}',
                                }
                            ],
                        }
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )

    assert tool.parse_session_final_answer(session) == "已完成。\nhttps://docs.example/doc"


def test_cron_final_report_finds_latest_matching_session(tmp_path: Path) -> None:
    session = tmp_path / "run.jsonl"
    session.write_text(
        json.dumps(
            {
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "done", "textSignature": '{"phase":"final_answer"}'}],
                },
                "sessionKey": "agent:main:cron:job_1:run:abc",
            }
        ),
        encoding="utf-8",
    )

    report = tool.cron_final_report("job_1", started_at=0, sessions_dir=tmp_path)

    assert report["found"] is True
    assert report["text"] == "done"


def test_cron_final_report_finds_job_id_beyond_file_head(tmp_path: Path) -> None:
    session = tmp_path / "run.jsonl"
    session.write_text(
        "x" * 25000
        + "\n"
        + json.dumps({"sessionKey": "agent:main:cron:job_deep:run:abc"})
        + "\n"
        + json.dumps(
            {
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "deep done", "textSignature": '{"phase":"final_answer"}'}],
                }
            }
        ),
        encoding="utf-8",
    )

    report = tool.cron_final_report("job_deep", started_at=0, sessions_dir=tmp_path)

    assert report["found"] is True
    assert report["text"] == "deep done"
