from __future__ import annotations

import json
from pathlib import Path

from harness_intent_agent import IntentFrame
from harness_tool_binder import bind_tool


def registry() -> dict:
    return json.loads((Path(__file__).resolve().parents[2] / "config" / "openclaw" / "intent_tools.json").read_text(encoding="utf-8"))


def frame(domain: str, action: str, candidates: list[dict] | None = None) -> IntentFrame:
    return IntentFrame(
        conversation_mode="task",
        domain=domain,
        action=action,
        canonical_text="canonical",
        context_refs=[],
        parameters={},
        safety="readonly",
        result_contract={},
        tool_candidates=candidates or [],
        confidence=0.9,
        reason="test",
    )


def test_binds_explicit_candidate() -> None:
    binding = bind_tool(frame("timescar", "query", [{"tool_id": "timescar.dm.query", "confidence": 0.9}]), registry())
    assert binding.status == "bound"
    assert binding.tool and binding.tool["tool_id"] == "timescar.dm.query"


def test_binds_by_domain_action_without_patterns() -> None:
    binding = bind_tool(frame("timescar", "query"), registry())
    assert binding.status == "bound"
    assert binding.tool and binding.tool["tool_id"] == "timescar.dm.query"


def test_unregistered_domain_action_becomes_gap() -> None:
    binding = bind_tool(frame("config", "query"), registry())
    assert binding.status == "gap"
    assert binding.tool is None
