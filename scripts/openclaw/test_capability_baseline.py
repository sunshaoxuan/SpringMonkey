from __future__ import annotations

import json
import tempfile
from pathlib import Path

import verify_capability_baseline as baseline
from harness_intent_agent import infer_intent_frame
from intent_tool_router import extract_args


def model_reply(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def test_capability_baseline_passes_static_contract_cases() -> None:
    results = baseline.verify_baseline(fail_open_model=False)
    failures = [item for item in results if not item.passed]
    assert not failures, failures
    assert any(item.case_id == "timescar_adjust_relative_this_booking" and not item.live_intent for item in results)
    assert any(item.case_id == "xhs_cron_status" and item.actual_tool_id == "openclaw.cron.status" for item in results)


def test_find_case_matches_exact_normalized_text() -> None:
    case = baseline.find_case(" 把这单的开始时间往后推24小时，结束时间不变。 ")
    assert case
    assert case["id"] == "timescar_adjust_relative_this_booking"


def test_xhs_cron_status_semantic_contract_and_args() -> None:
    registry = baseline.load_json(baseline.DEFAULT_REGISTRY)
    frame = infer_intent_frame(
        "检查每3天一次的小红书文章撰写任务状态。",
        context="",
        registry=registry,
        model_caller=lambda _messages: model_reply(
            {
                "conversation_mode": "task",
                "domain": "cron",
                "action": "status",
                "canonical_text": "检查每3天一次的小红书文章撰写任务状态。",
                "context_refs": [],
                "parameters": {"topic": "xhs"},
                "safety": "readonly",
                "result_contract": {"type": "cron_status", "topic": "xhs"},
                "tool_candidates": [{"tool_id": "openclaw.cron.status", "confidence": 0.98, "reason": "semantic ToolContract match"}],
                "confidence": 0.98,
                "reason": "recurring task status",
            }
        ),
    )
    assert frame.source == "model"
    assert frame.domain == "cron"
    assert frame.action == "status"
    assert frame.tool_candidates[0]["tool_id"] == "openclaw.cron.status"
    tool = next(item for item in registry["tools"] if item["tool_id"] == "openclaw.cron.status")
    args = extract_args(tool, frame.canonical_text, "2026-05-08T23:00:00+09:00")
    args["_model_intent_frame"] = frame.__dict__
    if frame.parameters.get("topic"):
        args["topic"] = frame.parameters["topic"]
    assert args["topic"] == "xhs"


def test_news_cron_status_tool_reads_news_jobs() -> None:
    from cron_status_tool import format_status

    with tempfile.TemporaryDirectory() as tmp:
        jobs = Path(tmp) / "jobs.json"
        jobs.write_text(
            json.dumps(
                {
                    "jobs": [
                        {
                            "id": "job_news",
                            "name": "news-digest-jst-1700",
                            "enabled": True,
                            "cron": "0 17 * * *",
                            "payload": {"model": "openai-codex/gpt-5.5"},
                        },
                        {
                            "id": "job_xhs",
                            "name": "xhs-recommendation-every-3-days",
                            "enabled": True,
                            "cron": "0 10 */3 * *",
                            "payload": {"model": "openai-codex/gpt-5.5"},
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        output = format_status("为什么公共频道的新闻停了", "news", jobs)
    assert "主题：news" in output
    assert "匹配数量：1" in output
    assert "news-digest-jst-1700" in output
    assert "xhs-recommendation" not in output


def test_recurring_cron_run_semantic_contract_and_args() -> None:
    registry = baseline.load_json(baseline.DEFAULT_REGISTRY)
    frame = infer_intent_frame(
        "接下来，请你开始执行每3天一次的小红书撰稿计划。",
        context="",
        registry=registry,
        model_caller=lambda _messages: model_reply(
            {
                "conversation_mode": "task",
                "domain": "cron",
                "action": "run",
                "canonical_text": "接下来，请你开始执行每3天一次的小红书撰稿计划。",
                "context_refs": [],
                "parameters": {"capability_id": "recurring.content_writing.every_3_days"},
                "safety": "write",
                "result_contract": {"type": "recurring_cron_run", "capability_id": "recurring.content_writing.every_3_days"},
                "tool_candidates": [{"tool_id": "openclaw.cron.run.recurring_job", "confidence": 0.98, "reason": "semantic ToolContract match"}],
                "confidence": 0.98,
                "reason": "manual run for configured recurring job",
            }
        ),
    )
    assert frame.domain == "cron"
    assert frame.action == "run"
    assert frame.safety == "write"
    assert frame.tool_candidates[0]["tool_id"] == "openclaw.cron.run.recurring_job"
    tool = next(item for item in registry["tools"] if item["tool_id"] == "openclaw.cron.run.recurring_job")
    args = extract_args(tool, frame.canonical_text, "2026-05-09T00:00:00+09:00")
    assert args["text"] == "接下来，请你开始执行每3天一次的小红书撰稿计划。"


def test_cron_status_tool_reads_jobs_json() -> None:
    from cron_status_tool import format_status

    with tempfile.TemporaryDirectory() as tmp:
        jobs = Path(tmp) / "jobs.json"
        jobs.write_text(
            json.dumps(
                {
                    "jobs": [
                        {
                            "id": "job_xhs",
                            "name": "xhs-recommendation-every-3-days",
                            "enabled": True,
                            "cron": "0 10 */3 * *",
                            "payload": {"model": "openai-codex/gpt-5.5"},
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        output = format_status("检查小红书任务", "xhs", jobs)
    assert "匹配数量：1" in output
    assert "xhs-recommendation-every-3-days" in output
    assert "openai-codex/gpt-5.5" in output
