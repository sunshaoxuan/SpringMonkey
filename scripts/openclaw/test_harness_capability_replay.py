from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from harness_dispatcher import handle_event
from harness_intent_agent import IntentFrame
from harness_intent_audit import IntentAuditResult, ResultEvaluation


def test_dispatcher_records_nonzero_tool_failure_and_replays_readonly_once() -> None:
    frame = IntentFrame(
        conversation_mode="task",
        domain="weather",
        action="query",
        canonical_text="请查询明天东京天气和风况",
        context_refs=[],
        parameters={},
        safety="readonly",
        result_contract={},
        tool_candidates=[{"tool_id": "weather.dm.query", "confidence": 0.99, "reason": "test"}],
        confidence=0.99,
        reason="test",
    )
    registry = {
        "tools": [
            {
                "intent_id": "weather.dm.query",
                "tool_id": "weather.dm.query",
                "entrypoint": "scripts/weather/handle_dm_weather_query.py",
                "args_schema": {"mode": "dm_text_timestamp", "force": False},
                "permission": "owner_dm",
                "write_operation": False,
                "reply_policy": "tool_stdout",
                "domain": "weather",
                "actions": ["query"],
            }
        ]
    }
    calls = {"count": 0}

    def run_tool(_tool, _args, _timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            return 2, "temporary capability_gap missing parameter bridge"
        return 0, "东京天气：晴。"

    def audit_intent(**kwargs):
        return IntentAuditResult("passed", kwargs["extracted_args"], {}, "ok", 1.0)

    def evaluate_result(_tool, _output, _contract):
        return ResultEvaluation(True, "ok", {}, {})

    blocker = {
        "intent_kind": "task",
        "blocker_kind": "readonly_tool_missing",
        "safety_class": "auto_safe_readonly",
        "confidence": 0.95,
        "expected_capability_family": "weather",
        "missing_condition": "readonly bridge missing",
        "allowed_repair_action": "verify existing readonly tool",
        "replay_policy": "allow_after_verified_promoted",
        "reasoning_summary": "readonly capability gap",
    }
    with tempfile.TemporaryDirectory() as tmp, patch("harness_dispatcher.infer_intent_frame", return_value=frame), patch(
        "dm_capability_gap_runner.run_verify_command", return_value=(True, "ok")
    ), patch("capability_blocker_classifier.call_model", return_value=(json.dumps(blocker, ensure_ascii=False), {"model": "test"})):
        result = handle_event(
            text="请查询明天东京天气和风况",
            channel="discord_dm",
            user_id="tester",
            message_timestamp="2026-05-08T01:00:00+09:00",
            registry=registry,
            context="",
            kernel_root=Path(tmp) / "kernel",
            timeout_seconds=10,
            extract_args=lambda _tool, text, ts: {"text": text, "message_timestamp": ts, "force": False},
            run_tool=run_tool,
            format_reply=lambda _tool, _args, _code, output: output,
            audit_intent=audit_intent,
            evaluate_result=evaluate_result,
        )
        events = (Path(tmp) / "kernel" / "capability_gap_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert result.status == "ok"
    assert calls["count"] == 2
    assert "自演进重放" in result.reply
    assert json.loads(events[-1])["replay_allowed"] is True
