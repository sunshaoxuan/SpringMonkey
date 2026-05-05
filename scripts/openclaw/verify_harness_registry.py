#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
HARNESS = REPO / "config" / "openclaw" / "harness.json"
SKILLS = REPO / "config" / "openclaw" / "skills.json"
TOOLS = REPO / "config" / "openclaw" / "intent_tools.json"

REQUIRED_LAYERS = {
    "agent_runtime",
    "skill_layer",
    "tool_layer",
    "context_layer",
    "governance_layer",
    "observability_layer",
}
REQUIRED_TOOL_KEYS = {
    "owner_agent",
    "input_schema",
    "output_schema",
    "invocation_log_policy",
    "permission_scope",
}


def fail(message: str) -> None:
    raise SystemExit(f"OPENCLAW_HARNESS_REGISTRY_FAIL: {message}")


def load(path: Path) -> dict:
    if not path.is_file():
        fail(f"missing file: {path.relative_to(REPO)}")
    return json.loads(path.read_text(encoding="utf-8"))


def verify() -> int:
    harness = load(HARNESS)
    skills = load(SKILLS)
    tools = load(TOOLS)
    if harness.get("schema_version") != 1:
        fail("harness schema_version must be 1")
    if skills.get("schema_version") != 1:
        fail("skills schema_version must be 1")

    layer_ids = {str(item.get("id")) for item in harness.get("layers", [])}
    missing_layers = sorted(REQUIRED_LAYERS - layer_ids)
    if missing_layers:
        fail(f"missing harness layers: {missing_layers}")

    subagents = {str(item.get("id")): item for item in harness.get("subagents", [])}
    for required in ("intentAgent", "plannerAgent", "toolWorker", "browserWorker", "newsWorker", "timescarWorker", "recoveryWorker", "evaluatorAgent"):
        if required not in subagents:
            fail(f"missing subagent: {required}")

    for index, skill in enumerate(skills.get("skills", [])):
        skill_id = str(skill.get("skill_id") or "")
        if not skill_id:
            fail(f"skill[{index}] missing skill_id")
        owner = str(skill.get("owner_agent") or "")
        if owner not in subagents:
            fail(f"{skill_id}: unknown owner_agent {owner}")
        for key in ("version", "domain", "entrypoints", "verify_commands", "publish_status", "rollback"):
            if not skill.get(key):
                fail(f"{skill_id}: missing {key}")
        for entrypoint in skill.get("entrypoints", []):
            if not (REPO / str(entrypoint)).exists():
                fail(f"{skill_id}: entrypoint not found: {entrypoint}")

    for tool in tools.get("tools", []):
        tool_id = str(tool.get("tool_id") or "")
        missing = sorted(REQUIRED_TOOL_KEYS - set(tool))
        if missing:
            fail(f"{tool_id}: missing harness tool keys: {missing}")
        owner = str(tool.get("owner_agent") or "")
        if owner not in subagents:
            fail(f"{tool_id}: unknown owner_agent {owner}")
        if not isinstance(tool.get("input_schema"), dict) or not isinstance(tool.get("output_schema"), dict):
            fail(f"{tool_id}: input_schema/output_schema must be objects")
        if not str(tool.get("invocation_log_policy") or ""):
            fail(f"{tool_id}: invocation_log_policy required")
        if bool(tool.get("write_operation")) and "write" not in str(tool.get("permission_scope") or ""):
            fail(f"{tool_id}: write operation permission_scope must include write")

    print(f"openclaw_harness_registry_ok layers={len(layer_ids)} subagents={len(subagents)} skills={len(skills.get('skills', []))} tools={len(tools.get('tools', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(verify())
