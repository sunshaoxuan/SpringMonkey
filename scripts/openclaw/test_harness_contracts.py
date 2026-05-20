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
    assert "prompt_hints" not in prompt


def test_contract_prompt_does_not_use_prompt_hints_as_examples() -> None:
    registry = {
        "tools": [
            {
                "tool_id": "demo.tool",
                "capability_id": "demo.tool",
                "domain": "cron",
                "actions": ["status"],
                "description": "Inspect a recurring job by semantic topic.",
                "prompt_hints": ["用户原话关键词不应进入语义契约"],
                "input_contract": {"type": "dm_text_timestamp"},
                "output_contract": {"type": "plain_text_business_result"},
                "permission_scope": "owner_dm_readonly",
                "write_operation": False,
                "safety": "readonly",
            }
        ]
    }

    prompt = harness_contracts.contract_prompt(registry)

    assert "用户原话关键词不应进入语义契约" not in prompt
    assert '"examples": []' in prompt


def test_intent_prompt_uses_contracts_not_registry_patterns() -> None:
    messages = harness_intent_agent.build_prompt("请处理这个任务", "", load_registry())
    user = messages[1]["content"]

    assert "Intent capability families:" in user
    assert "Registered ToolContracts:" in user
    assert "required_any" not in user
    assert "patterns" not in user
    assert "prompt_hints" not in user
