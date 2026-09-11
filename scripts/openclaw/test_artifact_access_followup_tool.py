from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import artifact_access_followup_tool as tool


def test_current_account_correction_overrides_configured_recipient() -> None:
    with patch.object(tool, "run_access_agent", return_value=(True, "已授权查看。")) as run:
        tool.build_reply(
            {"job_name": "content-job"}, "https://docs.google.com/document/d/example/edit",
            execute_agent=True, owner_email="previous@example.com",
            request_text="我又申请了一个，账号应该是correct@example.com",
        )
    assert run.call_args.args[1] == "correct@example.com"


def test_multiple_accounts_require_disambiguation_without_sharing() -> None:
    with patch.object(tool, "run_access_agent") as run:
        reply = tool.build_reply(
            {"job_name": "content-job"}, "https://docs.google.com/document/d/example/edit",
            execute_agent=True, owner_email="previous@example.com",
            request_text="previous@example.com correct@example.com",
        )
    run.assert_not_called()
    assert "等待明确授权账号" in reply


def test_missing_override_uses_configured_account() -> None:
    assert tool.resolve_recipient("请给刚才的文档开权限", "owner@example.com") == "owner@example.com"


def test_artifact_access_followup_reports_access_work_not_generation_status(tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    state.write_text(
        json.dumps(
            {"source": "content-job", "url": "https://docs.google.com/document/d/example123/edit?usp=sharing"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    task, doc_url = tool.resolve_artifact("刚才的文档", artifact_state=state)
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
    assert command[command.index("--model") + 1] == "openai-codex/gpt-5.6-sol"
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
    state = tmp_path / "latest.json"
    state.write_text(json.dumps({"url": "https://docs.google.com/document/d/old/edit"}), encoding="utf-8")

    task, doc_url = tool.resolve_artifact(
        "请授权 https://docs.google.com/document/d/explicit/edit",
        artifact_state=state,
    )

    assert task and task["job_name"] == "explicit artifact URL"
    assert doc_url == "https://docs.google.com/document/d/explicit/edit"


def test_authoritative_artifact_registry_resolves_implicit_followup(tmp_path: Path) -> None:
    state = tmp_path / "latest.json"
    state.write_text(
        json.dumps(
            {
                "url": "https://docs.google.com/document/d/current/edit",
                "source": "xhs-recommendation-every-3-days",
            }
        ),
        encoding="utf-8",
    )

    task, doc_url = tool.resolve_artifact("给刚才的文档开权限", artifact_state=state)

    assert task and task["job_name"] == "xhs-recommendation-every-3-days"
    assert doc_url == "https://docs.google.com/document/d/current/edit"
