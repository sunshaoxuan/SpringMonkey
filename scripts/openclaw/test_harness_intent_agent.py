from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import harness_intent_agent as agent


def load_registry() -> dict:
    return json.loads((Path(__file__).resolve().parents[2] / "config" / "openclaw" / "intent_tools.json").read_text(encoding="utf-8"))


def model_reply(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def test_intent_frame_timescar_month_query() -> None:
    with tempfile.TemporaryDirectory() as tmp, patch.dict(agent.os.environ, {"OPENCLAW_HARNESS_MODEL_CALL_LOG": str(Path(tmp) / "model.jsonl")}):
        frame = agent.infer_intent_frame(
            "帮我查未来一个月的订车记录",
            context="",
            registry=load_registry(),
            model_caller=lambda _messages: model_reply(
                {
                    "conversation_mode": "task",
                    "domain": "timescar",
                    "action": "query",
                    "canonical_text": "查询 TimesCar 预约 未来一个月",
                    "context_refs": [],
                    "parameters": {"duration_hours": 720, "offset_hours": 0, "relation": "within"},
                    "safety": "readonly",
                    "result_contract": {"type": "timescar_query_range"},
                    "tool_candidates": [{"tool_id": "timescar.dm.query", "confidence": 0.98, "reason": "registered query capability"}],
                    "confidence": 0.98,
                    "reason": "TimesCar reservation query",
                }
            ),
        )
    assert frame.domain == "timescar"
    assert frame.action == "query"
    assert frame.parameters["duration_hours"] == 720
    assert frame.parameters["offset_hours"] == 0


def test_intent_frame_chat_has_no_tool() -> None:
    frame = agent.infer_intent_frame(
        "你好",
        context="",
        registry=load_registry(),
        model_caller=lambda _messages: model_reply(
            {
                "conversation_mode": "chat",
                "domain": "general",
                "action": "chat",
                "canonical_text": "你好，我在。",
                "context_refs": [],
                "parameters": {},
                "safety": "readonly",
                "result_contract": {},
                "tool_candidates": [],
                "confidence": 0.99,
                "reason": "greeting",
            }
        ),
    )
    assert frame.conversation_mode == "chat"
    assert frame.tool_candidates == []


def test_invalid_intent_frame_is_rejected() -> None:
    try:
        agent.validate_intent_frame({"conversation_mode": "task", "domain": "bad", "action": "query"})
        raise AssertionError("invalid domain should fail")
    except ValueError:
        pass
