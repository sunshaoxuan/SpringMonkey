#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "config" / "openclaw" / "intent_tools.json"


def load_tool():
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    matches = [tool for tool in data.get("tools", []) if tool.get("tool_id") == "openclaw.self_evolution.internal_repair"]
    assert len(matches) == 1
    return matches[0]


def test_registry_contains_generic_self_evolution_internal_repair_tool():
    tool = load_tool()
    assert tool["intent_id"] == "openclaw.self_evolution.internal_repair"
    assert tool["entrypoint"] == "scripts/openclaw/self_evolution_internal_repair.py"
    assert tool["args_schema"]["mode"] == "self_evolution_internal_repair"
    assert tool["permission"] == "owner_dm_write"
    assert tool["permission_scope"] == "owner_dm_write"
    assert tool["write_operation"] is True
    assert "test_self_evolution_internal_repair_router.py" in tool["verify_command"]
    assert tool["domain"] == "self"
    assert set(tool["actions"]) >= {"repair", "implement", "verify", "push"}
    generic_fields = {key: value for key, value in tool.items() if key != "verify_command"}
    encoded = json.dumps(generic_fields, ensure_ascii=False).lower()
    assert "天气" not in encoded
    assert "weather" not in encoded
    # The verification command may include domain regression suites; that is not
    # a router/business keyword branch in the self-evolution contract itself.
    assert "test_weather_image_forecast.py" in tool["verify_command"]


def test_registry_documents_public_release_approval_gate():
    tool = load_tool()
    encoded = json.dumps(tool, ensure_ascii=False).lower()
    assert "approval" in encoded or "审批" in encoded or "批准" in encoded
    assert "public" in encoded or "公共" in encoded
    assert "do_not_use_when" in tool


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print(f"{Path(__file__).name}: ok")
