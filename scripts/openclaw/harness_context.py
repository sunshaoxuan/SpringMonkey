#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")


@dataclass
class HarnessContextBundle:
    trace_id: str
    intent: str
    channel: str
    user_id: str
    dm_context: str
    business_context: str
    registry_summary: str
    recent_invocations: str
    memory_refs: list[str]
    rag_refs: list[str]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def registry_summary(limit: int = 24) -> str:
    registry = read_json(REPO / "config" / "openclaw" / "intent_tools.json")
    tools = [
        {
            "tool_id": item.get("tool_id"),
            "intent_id": item.get("intent_id"),
            "owner_agent": item.get("owner_agent"),
            "write_operation": item.get("write_operation"),
        }
        for item in registry.get("tools", [])[:limit]
    ]
    return json.dumps(tools, ensure_ascii=False)


def latest_business_context(intent: str) -> str:
    if "timescar" in intent:
        trace_dir = WORKSPACE / "state" / "timescar_traces"
        if not trace_dir.is_dir():
            return ""
        candidates = sorted(trace_dir.glob("*.latest.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        snippets: list[str] = []
        for path in candidates[:3]:
            try:
                data = read_json(path)
            except Exception:
                continue
            final_message = str(data.get("finalMessage") or "").strip()
            if final_message:
                snippets.append(f"{path.name}: {final_message[:700]}")
        return "\n".join(snippets)
    return ""


def latest_invocation_context(limit: int = 5) -> str:
    path = WORKSPACE / "var" / "harness_tool_invocations.jsonl"
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-50:]
    except OSError:
        return ""
    snippets: list[str] = []
    for raw in reversed(lines):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        tool_id = str(payload.get("tool_id") or "")
        if not tool_id:
            continue
        input_summary = str(payload.get("input_summary") or "").strip()
        result_summary = str(payload.get("result_summary") or "").strip()
        trace_id = str(payload.get("trace_id") or "").strip()
        snippets.append(
            json.dumps(
                {
                    "tool_id": tool_id,
                    "trace_id": trace_id,
                    "input": input_summary[:240],
                    "result": result_summary[:500],
                },
                ensure_ascii=False,
            )
        )
        if len(snippets) >= limit:
            break
    return "\n".join(reversed(snippets))


def build_context_bundle(
    *,
    trace_id: str,
    intent: str,
    channel: str,
    user_id: str,
    dm_context: str = "",
    include_business_context: bool = True,
    include_registry: bool = True,
) -> HarnessContextBundle:
    return HarnessContextBundle(
        trace_id=trace_id,
        intent=intent,
        channel=channel,
        user_id=user_id,
        dm_context=dm_context if channel == "discord_dm" else "",
        business_context=latest_business_context(intent) if include_business_context else "",
        registry_summary=registry_summary() if include_registry else "",
        recent_invocations=latest_invocation_context() if channel == "discord_dm" else "",
        memory_refs=[],
        rag_refs=[],
    )


def context_to_prompt(bundle: HarnessContextBundle) -> str:
    return "\n".join(
        [
            f"trace_id={bundle.trace_id}",
            f"intent={bundle.intent}",
            f"channel={bundle.channel}",
            f"user_id={bundle.user_id}",
            "DM context:",
            bundle.dm_context or "(none)",
            "Business context:",
            bundle.business_context or "(none)",
            "Registry summary:",
            bundle.registry_summary or "(not loaded)",
            "Recent tool invocations:",
            bundle.recent_invocations or "(none)",
        ]
    )
