from __future__ import annotations

import json
from pathlib import Path

from harness_intent_agent import IntentFrame
from harness_semantic_reviewer import review_intent_frame


def registry() -> dict:
    return json.loads((Path(__file__).resolve().parents[2] / "config" / "openclaw" / "intent_tools.json").read_text(encoding="utf-8"))


def tool(tool_id: str) -> dict:
    return next(item for item in registry()["tools"] if item["tool_id"] == tool_id)


def frame(**overrides) -> IntentFrame:
    values = {
        "conversation_mode": "task",
        "domain": "timescar",
        "action": "query",
        "canonical_text": "查询 TimesCar 预约 未来一个月以后",
        "context_refs": [],
        "parameters": {"duration_hours": 720, "offset_hours": 720, "relation": "after"},
        "safety": "readonly",
        "result_contract": {},
        "tool_candidates": [{"tool_id": "timescar.dm.query"}],
        "confidence": 0.9,
        "reason": "test",
    }
    values.update(overrides)
    return IntentFrame(**values)


def test_reviewer_accepts_matching_offset_semantics() -> None:
    review = review_intent_frame(frame(), tool("timescar.dm.query"), "未来一个月以后")
    assert review.passed


def test_reviewer_rejects_wrong_offset_semantics() -> None:
    review = review_intent_frame(frame(parameters={"duration_hours": 720, "offset_hours": 0, "relation": "within"}), tool("timescar.dm.query"), "未来一个月以后")
    assert not review.passed
    assert review.conflict_type == "semantic_verifier_conflict"


def test_reviewer_rejects_write_tool_marked_readonly() -> None:
    review = review_intent_frame(frame(action="cancel", safety="readonly"), tool("timescar.dm.cancel_next"), "取消这单")
    assert not review.passed
    assert review.conflict_type == "safety_mismatch"
