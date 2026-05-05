#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ToolInvocationRecord:
    trace_id: str
    task_id: str
    tool_id: str
    owner_agent: str
    status: str
    latency_ms: int
    result_summary: str
    permission_scope: str
    created_at: str = field(default_factory=utc_now)


@dataclass
class EvaluationRecord:
    trace_id: str
    evaluator_agent: str
    passed: bool
    reason: str
    result_contract: str
    actual_result: str = ""
    gap_type: str = ""
    created_at: str = field(default_factory=utc_now)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def record_tool_invocation(record: ToolInvocationRecord, path: Path | None = None) -> Path:
    target = path or Path(os.environ.get("OPENCLAW_HARNESS_TOOL_INVOCATION_LOG", "")) if os.environ.get("OPENCLAW_HARNESS_TOOL_INVOCATION_LOG") else path or (WORKSPACE / "var" / "harness_tool_invocations.jsonl")
    append_jsonl(target, asdict(record))
    return target


def record_evaluation(record: EvaluationRecord, path: Path | None = None) -> Path:
    target = path or Path(os.environ.get("OPENCLAW_HARNESS_EVALUATION_LOG", "")) if os.environ.get("OPENCLAW_HARNESS_EVALUATION_LOG") else path or (WORKSPACE / "var" / "harness_evaluations.jsonl")
    append_jsonl(target, asdict(record))
    return target
