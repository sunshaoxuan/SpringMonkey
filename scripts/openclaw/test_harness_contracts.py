from __future__ import annotations

import json
from pathlib import Path

import harness_contracts
import harness_intent_agent


def load_registry() -> dict:
    return json.loads((Path(__file__).resolve().parents[2] / "config" / "openclaw" / "intent_tools.json").read_text(encoding="utf-8"))


def test_tool_contract_prompt_excludes_pattern_matching_fields() -> None:
    prompt = harness_contracts.contract_prompt(load_registry(), limit=3)

    assert "ToolContract" not in prompt
    assert "use_when" in prompt
    assert "do_not_use_when" in prompt
    assert "input_contract" in prompt
    assert "patterns" not in prompt
    assert "required_any" not in prompt


def test_intent_prompt_uses_contracts_not_registry_patterns() -> None:
    messages = harness_intent_agent.build_prompt("请处理这个任务", "", load_registry())
    user = messages[1]["content"]

    assert "Intent capability families:" in user
    assert "Registered ToolContracts:" in user
    assert "required_any" not in user
    assert "patterns" not in user
