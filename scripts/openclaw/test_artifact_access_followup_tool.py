from __future__ import annotations

import json
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
        ok, result = tool.run_access_agent("https://docs.google.com/document/d/example/edit", timeout_seconds=30)

    assert ok is True
    assert result == "已授权查看。"
    assert "--json" in run.call_args.args[0]
