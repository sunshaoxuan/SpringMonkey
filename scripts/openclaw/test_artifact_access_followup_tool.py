from __future__ import annotations

import json
import uuid
import os
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import artifact_access_followup_tool as tool


def test_artifact_access_followup_reports_access_work_not_generation_status(tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    state.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "job_name": "content-job",
                        "status": "delivered",
                        "final_report": "已写入 https://docs.google.com/document/d/example123/edit?usp=sharing",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    task, doc_url = tool.latest_artifact(tool.load_tasks(state))
    reply = tool.build_reply(task, doc_url)

    assert "交付物访问请求已识别" in reply
    assert "不是文件生成状态查询" in reply
    assert "https://docs.google.com/document/d/example123/edit?usp=sharing" in reply
    assert "尚未证明 Google Docs 查看权限已经授予" in reply


def test_run_access_agent_extracts_final_authorization_result() -> None:
    completed = SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"status": "ok", "result": {"payloads": [{"text": "已授权查看。"}]}}, ensure_ascii=False),
    )
    with patch.object(tool.subprocess, "run", return_value=completed) as run:
        ok, result = tool.run_access_agent(
            "https://docs.google.com/document/d/example/edit",
            "owner@example.com",
            timeout_seconds=30,
        )

    assert ok is True
    assert result == "已授权查看。"
    assert "--json" in run.call_args.args[0]
    command = run.call_args.args[0]
    session_id = command[command.index("--session-id") + 1]
    assert uuid.UUID(session_id).version == 4
    prompt = run.call_args.args[0][run.call_args.args[0].index("--message") + 1]
    assert "owner@example.com" in prompt
    assert "不要创建公开链接" in prompt


def test_access_execution_requires_configured_owner_email(tmp_path: Path) -> None:
    task = {
        "job_name": "content-job",
        "final_report": "https://docs.google.com/document/d/example/edit",
    }

    with patch.object(tool, "run_access_agent") as run:
        reply = tool.build_reply(task, "https://docs.google.com/document/d/example/edit", execute_agent=True)

    assert "未配置 OPENCLAW_OWNER_GOOGLE_EMAIL" in reply
    run.assert_not_called()


def test_explicit_document_url_wins_over_cached_artifact(tmp_path: Path) -> None:
    cached = [{"job_name": "old", "final_report": "https://docs.google.com/document/d/old/edit"}]

    task, doc_url = tool.resolve_artifact(
        "请授权 https://docs.google.com/document/d/explicit/edit",
        cached,
        jobs_path=tmp_path / "missing-jobs.json",
        sessions_dir=tmp_path / "missing-sessions",
    )

    assert task and task["job_name"] == "explicit artifact URL"
    assert doc_url == "https://docs.google.com/document/d/explicit/edit"


def test_latest_cron_final_artifact_wins_over_stale_task_cache(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs.json"
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    jobs.write_text(json.dumps({"jobs": [{"id": "job-new"}]}), encoding="utf-8")
    session = sessions / "new.jsonl"
    rows = [
        {"sessionKey": "agent:main:cron:job-new:run:one"},
        {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "已写入 https://docs.google.com/document/d/current/edit",
                        "textSignature": '{"phase":"final_answer"}',
                    }
                ],
            }
        },
    ]
    session.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    os.utime(session, (2_000_000_000, 2_000_000_000))
    cached = [{"job_name": "old", "final_report": "https://docs.google.com/document/d/old/edit"}]

    task, doc_url = tool.resolve_artifact("给刚才的文档开权限", cached, jobs_path=jobs, sessions_dir=sessions)

    assert task and task["job_name"] == "latest cron artifact"
    assert doc_url == "https://docs.google.com/document/d/current/edit"
