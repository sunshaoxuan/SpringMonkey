from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import artifact_update_followup_tool as tool


def test_artifact_update_followup_reports_update_work_not_gap(tmp_path: Path) -> None:
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
    reply = tool.build_reply("补充三张图片", task, doc_url)

    assert "交付物更新请求已识别" in reply
    assert "不是任务状态查询" in reply
    assert "https://docs.google.com/document/d/example123/edit?usp=sharing" in reply
    assert "尚未证明后续修改完成" in reply


def test_run_update_agent_extracts_final_update_result() -> None:
    completed = SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"status": "ok", "result": {"payloads": [{"text": "已更新交付物：补充了三张图片。"}]}}, ensure_ascii=False),
    )
    with patch.object(tool.subprocess, "run", return_value=completed) as run:
        ok, result = tool.run_update_agent("补充三张图片", "https://docs.google.com/document/d/example/edit", timeout_seconds=30)

    assert ok is True
    assert result == "已更新交付物：补充了三张图片。"
    assert "--json" in run.call_args.args[0]
