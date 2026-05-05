#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "config" / "openclaw" / "intent_tools.json"
REQUIRED_KEYS = {
    "intent_id",
    "tool_id",
    "capability_id",
    "domain",
    "actions",
    "prompt_hints",
    "entrypoint",
    "args_schema",
    "permission",
    "write_operation",
    "input_contract",
    "output_contract",
    "permission_scope",
    "worker_agent",
    "verify_command",
    "failure_policy",
}


def fail(message: str) -> None:
    raise SystemExit(f"INTENT_TOOL_REGISTRY_FAIL: {message}")


def main() -> int:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        fail("schema_version must be 1")
    tools = data.get("tools")
    if not isinstance(tools, list) or not tools:
        fail("tools must be a non-empty list")

    seen_intents: set[str] = set()
    seen_tools: set[str] = set()
    for index, tool in enumerate(tools):
        missing = sorted(REQUIRED_KEYS - set(tool))
        if missing:
            fail(f"tool[{index}] missing keys: {missing}")
        intent_id = str(tool["intent_id"])
        tool_id = str(tool["tool_id"])
        if intent_id in seen_intents:
            fail(f"duplicate intent_id: {intent_id}")
        if tool_id in seen_tools:
            fail(f"duplicate tool_id: {tool_id}")
        seen_intents.add(intent_id)
        seen_tools.add(tool_id)

        if not isinstance(tool.get("actions"), list) or not tool.get("actions"):
            fail(f"{tool_id}: actions must be a non-empty list")
        if not isinstance(tool.get("prompt_hints"), list):
            fail(f"{tool_id}: prompt_hints must be a list")
        if not isinstance(tool.get("input_contract"), dict) or not isinstance(tool.get("output_contract"), dict):
            fail(f"{tool_id}: input_contract/output_contract must be objects")
        entrypoint = REPO / str(tool["entrypoint"])
        if not entrypoint.is_file():
            fail(f"{tool_id}: entrypoint not found: {entrypoint}")
        schema = tool.get("args_schema")
        if not isinstance(schema, dict) or not schema.get("mode"):
            fail(f"{tool_id}: args_schema.mode is required")
        if bool(tool["write_operation"]):
            if not tool.get("confirm_policy"):
                fail(f"{tool_id}: write_operation requires confirm_policy")
            if not tool.get("idempotency"):
                fail(f"{tool_id}: write_operation requires idempotency")
            if "write" not in str(tool.get("permission", "")):
                fail(f"{tool_id}: write_operation permission must be write-scoped")
        verify_command = str(tool.get("verify_command") or "").strip()
        if not verify_command:
            fail(f"{tool_id}: verify_command required")
    print(f"intent_tool_registry_ok tools={len(tools)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
