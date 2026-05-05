from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import web_research_tool as tool
from harness_intent_audit import evaluate_result


def test_missing_brave_key_reports_concrete_failure() -> None:
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        tool.os.environ,
        {
            "OPENCLAW_HARNESS_WEB_RESEARCH_LOG": str(Path(tmp) / "research.jsonl"),
            "BRAVE_API_KEY": "",
            "OPENCLAW_BRAVE_API_KEY": "",
        },
        clear=False,
    ), patch.object(tool, "load_runtime_env_files", return_value=None):
        code, reply, evidence = tool.run_research("帮我查一下 OpenClaw 最新版本")
    assert code == 4
    assert "missing_brave_api_key" in reply
    assert "search_attempted=true" in reply
    assert evidence.search_attempted is True


def test_successful_search_fetch_outputs_sources_and_evidence() -> None:
    search = [tool.SearchResult(title="Example", url="https://example.com", snippet="snippet")]
    fetched = tool.FetchResult(url="https://example.com", ok=True, status=200, title="Example Domain", text="Example public page content")
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        tool.os.environ,
        {"OPENCLAW_HARNESS_WEB_RESEARCH_LOG": str(Path(tmp) / "research.jsonl")},
    ), patch.object(tool, "brave_search", return_value=search), patch.object(tool, "fetch_page", return_value=fetched), patch.object(
        tool, "summarize_with_model", return_value="- 示例页面说明了公开内容。"
    ):
        code, reply, evidence = tool.run_research("帮我查一下 Example")
        saved = json.loads((Path(tmp) / "research.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert code == 0
    assert "状态：成功" in reply
    assert "https://example.com" not in reply
    assert "来源链接已记录在后台日志" in reply
    assert "search_attempted=true" in reply
    assert "fetch_attempted=true" in reply
    assert evidence.sources[0]["url"] == "https://example.com"
    assert saved["sources"][0]["url"] == "https://example.com"


def test_result_evaluator_rejects_no_network_attempt() -> None:
    result = evaluate_result(
        {"tool_id": "openclaw.web.research"},
        "联网检索未完成\n状态：失败\n原因：unknown\n检索证据：search_attempted=false fetch_attempted=false browser_attempted=false sources=0",
        {"type": "web_research"},
    )
    assert not result.passed
    assert result.gap_type == "research_not_attempted"


def test_result_evaluator_accepts_concrete_failure() -> None:
    result = evaluate_result(
        {"tool_id": "openclaw.web.research"},
        "联网检索未完成\n状态：失败\n原因：RuntimeError: missing_brave_api_key\n检索证据：search_attempted=true fetch_attempted=false browser_attempted=false sources=0",
        {"type": "web_research"},
    )
    assert result.passed
