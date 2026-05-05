#!/usr/bin/env python3
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
DEFAULT_HARNESS = REPO / "config" / "openclaw" / "harness.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class HarnessTaskEnvelope:
    task_id: str
    trace_id: str
    intent: str
    context_refs: list[str]
    required_permissions: list[str]
    assigned_agent: str
    status: str
    result_contract: str
    source_channel: str
    user_id: str
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


def load_harness(path: Path = DEFAULT_HARNESS) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def subagent_ids(harness: dict[str, Any]) -> set[str]:
    return {str(item["id"]) for item in harness.get("subagents", [])}


def build_task_envelope(
    *,
    intent: str,
    assigned_agent: str,
    source_channel: str,
    user_id: str,
    required_permissions: list[str] | None = None,
    context_refs: list[str] | None = None,
    result_contract: str = "produce a user-visible result and machine-verifiable trace",
    harness: dict[str, Any] | None = None,
) -> HarnessTaskEnvelope:
    data = harness or load_harness()
    if assigned_agent not in subagent_ids(data):
        raise ValueError(f"unknown assigned_agent: {assigned_agent}")
    trace_prefix = str((data.get("trace_policy") or {}).get("trace_id_prefix") or "trace")
    return HarnessTaskEnvelope(
        task_id=make_id("task"),
        trace_id=make_id(trace_prefix),
        intent=intent,
        context_refs=context_refs or [],
        required_permissions=required_permissions or [],
        assigned_agent=assigned_agent,
        status="pending",
        result_contract=result_contract,
        source_channel=source_channel,
        user_id=user_id,
    )


def envelope_to_json(envelope: HarnessTaskEnvelope) -> str:
    return json.dumps(asdict(envelope), ensure_ascii=False, sort_keys=True)
