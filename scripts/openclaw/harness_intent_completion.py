#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nl_time_range import requested_range_hours


WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")
QUERY_ACTION_TOOLS = {"timescar.dm.query"}
TIMESCAR_QUERY_CONTEXT_RE = re.compile(r"(TimesCar|timescar|订车|訂車|预约|預約|予約|查询|查詢|检查|檢查|查看|列表|记录|記錄)")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class IntentCompletion:
    completed: bool
    tool_id: str | None
    canonical_text: str
    reason: str
    inherited_from: dict[str, Any] = field(default_factory=dict)
    parameter_overrides: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    created_at: str = field(default_factory=utc_now)


def completion_log_path() -> Path:
    configured = os.environ.get("OPENCLAW_HARNESS_INTENT_COMPLETION_LOG", "").strip()
    return Path(configured) if configured else WORKSPACE / "var" / "harness_intent_completions.jsonl"


def invocation_log_path(path: Path | None = None) -> Path:
    if path:
        return path
    configured = os.environ.get("OPENCLAW_HARNESS_TOOL_INVOCATION_LOG", "").strip()
    return Path(configured) if configured else WORKSPACE / "var" / "harness_tool_invocations.jsonl"


def append_completion(record: IntentCompletion, path: Path | None = None) -> Path:
    target = path or completion_log_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")
    return target


def recent_invocation(path: Path | None = None, *, allowed_tools: set[str] | None = None) -> dict[str, Any] | None:
    target = invocation_log_path(path)
    if not target.is_file():
        return None
    try:
        lines = target.read_text(encoding="utf-8").splitlines()[-50:]
    except OSError:
        return None
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        tool_id = str(payload.get("tool_id") or "")
        if tool_id and (allowed_tools is None or tool_id in allowed_tools):
            return payload
    return None


def complete_implicit_intent(text: str, context: str = "", invocation_path: Path | None = None) -> IntentCompletion:
    raw = (text or "").strip()
    range_hours = requested_range_hours(raw)
    if range_hours is None:
        return IntentCompletion(False, None, raw, "no parameter override detected")
    combined = f"{context}\n{raw}"
    if TIMESCAR_QUERY_CONTEXT_RE.search(combined):
        canonical = raw if TIMESCAR_QUERY_CONTEXT_RE.search(raw) else f"查询 TimesCar 预约 {raw}"
        result = IntentCompletion(
            True,
            "timescar.dm.query",
            canonical,
            "explicit TimesCar/query context plus range parameter",
            parameter_overrides={"requested_hours": range_hours},
            confidence=0.96,
        )
        append_completion(result)
        return result
    recent = recent_invocation(invocation_path, allowed_tools=QUERY_ACTION_TOOLS)
    if recent:
        result = IntentCompletion(
            True,
            str(recent.get("tool_id")),
            f"查询 TimesCar 预约 {raw}",
            "inherited recent read-only query intent and overrode range parameter",
            inherited_from={
                "trace_id": recent.get("trace_id"),
                "task_id": recent.get("task_id"),
                "tool_id": recent.get("tool_id"),
                "input_summary": recent.get("input_summary", ""),
            },
            parameter_overrides={"requested_hours": range_hours},
            confidence=0.9,
        )
        append_completion(result)
        return result
    result = IntentCompletion(False, None, raw, "range parameter present but no safe query context to inherit", parameter_overrides={"requested_hours": range_hours})
    append_completion(result)
    return result
