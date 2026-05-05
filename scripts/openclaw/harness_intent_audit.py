#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from harness_intent_completion import complete_implicit_intent
from nl_time_range import requested_range_hours, requested_range_spec


WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class IntentAuditResult:
    audit_status: str
    corrected_args: dict[str, Any]
    result_contract: dict[str, Any]
    reason: str
    confidence: float
    created_at: str = field(default_factory=utc_now)


@dataclass
class ResultEvaluation:
    passed: bool
    reason: str
    result_contract: dict[str, Any]
    actual: dict[str, Any]
    gap_type: str | None = None


QUERY_RANGE_PATTERN = re.compile(r"范围：\s*([0-9T:+-]+)\s+至\s+([0-9T:+-]+)")
CORRECTION_PATTERN = re.compile(r"(我说的是|我說的是|不是这个范围|不是這個範圍|时间段不对|時間段不對|查错|查錯|不对吧|不對吧)")
TIMESCAR_QUERY_CONTEXT_PATTERN = re.compile(r"(TimesCar|timescar|订车|訂車|预约|預約|予約|查询|查詢|检查|檢查|查看|列表|记录|記錄)")


def audit_log_path() -> Path:
    configured = os.environ.get("OPENCLAW_HARNESS_INTENT_AUDIT_LOG", "").strip()
    return Path(configured) if configured else WORKSPACE / "var" / "harness_intent_audits.jsonl"


def append_audit(record: IntentAuditResult, path: Path | None = None) -> Path:
    target = path or audit_log_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")
    return target


def requested_timescar_query_hours(text: str) -> int | None:
    return requested_range_hours(text)


def build_result_contract(tool: dict[str, Any], text: str, args: dict[str, Any]) -> dict[str, Any]:
    tool_id = str(tool.get("tool_id") or "")
    contract: dict[str, Any] = {"tool_id": tool_id}
    if tool_id == "timescar.dm.query":
        spec = requested_range_spec(text)
        requested_hours = spec.duration_hours if spec else None
        offset_hours = spec.offset_hours if spec else 0
        contract.update(
            {
                "type": "timescar_query_range",
                "requested_hours": requested_hours or 24,
                "offset_hours": offset_hours,
                "relation": spec.relation if spec else "within",
                "explicit_range_requested": requested_hours is not None,
            }
        )
        if args.get("message_timestamp"):
            try:
                start = parse_iso_minute(str(args["message_timestamp"])) + timedelta(hours=offset_hours)
                end = start + timedelta(hours=int(contract["requested_hours"]))
                contract["expected_range_start"] = start.isoformat(timespec="minutes")
                contract["expected_range_end"] = end.isoformat(timespec="minutes")
            except Exception:
                pass
    return contract


def audit_intent(
    *,
    text: str,
    context: str,
    selected_tool: dict[str, Any],
    extracted_args: dict[str, Any],
) -> IntentAuditResult:
    corrected_args = dict(extracted_args)
    completion = complete_implicit_intent(str(corrected_args.get("text") or text), context)
    if completion.completed and completion.tool_id == selected_tool.get("tool_id"):
        corrected_args["text"] = completion.canonical_text
        corrected_args["_intent_completion"] = asdict(completion)
    contract = build_result_contract(selected_tool, text, corrected_args)
    reason = "tool and extracted args are mechanically consistent"
    confidence = 0.9
    if selected_tool.get("tool_id") == "timescar.dm.query" and contract.get("explicit_range_requested"):
        requested_hours = int(contract["requested_hours"])
        corrected_args["_requested_range_hours"] = requested_hours
        corrected_args["_requested_offset_hours"] = int(contract.get("offset_hours") or 0)
        corrected_args["_intent_audit_context_used"] = bool(context)
        if not TIMESCAR_QUERY_CONTEXT_PATTERN.search(str(corrected_args.get("text") or "")):
            corrected_args["text"] = f"查询 TimesCar 预约 {corrected_args.get('text') or text}"
            corrected_args["_intent_audit_implied_query"] = True
        reason = f"timescar query range contract requested_hours={requested_hours}"
        confidence = 0.98
    result = IntentAuditResult("passed", corrected_args, contract, reason, confidence)
    append_audit(result)
    return result


def parse_iso_minute(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_timescar_output_range(output: str) -> dict[str, Any]:
    match = QUERY_RANGE_PATTERN.search(output or "")
    if not match:
        return {}
    start = parse_iso_minute(match.group(1))
    end = parse_iso_minute(match.group(2))
    hours = (end - start).total_seconds() / 3600
    return {
        "range_start": start.isoformat(timespec="minutes"),
        "range_end": end.isoformat(timespec="minutes"),
        "range_hours": hours,
    }


def evaluate_result(tool: dict[str, Any], output: str, result_contract: dict[str, Any]) -> ResultEvaluation:
    if str(tool.get("tool_id") or "") != "timescar.dm.query":
        return ResultEvaluation(True, "no mechanical evaluator required for this tool", result_contract, {})
    actual = parse_timescar_output_range(output)
    requested_hours = int(result_contract.get("requested_hours") or 24)
    if not actual:
        return ResultEvaluation(
            False,
            "TimesCar query output did not include a parseable range line",
            result_contract,
            actual,
            "registered_tool_parameter_gap",
        )
    actual_hours = float(actual.get("range_hours") or 0)
    expected_start = result_contract.get("expected_range_start")
    actual_start = actual.get("range_start")
    if expected_start and actual_start and parse_iso_minute(str(actual_start)) < parse_iso_minute(str(expected_start)) - timedelta(minutes=2):
        return ResultEvaluation(
            False,
            f"expected range to start at {expected_start} but tool output started at {actual_start}",
            result_contract,
            actual,
            "registered_tool_parameter_gap",
        )
    if actual_hours + 0.1 < requested_hours:
        return ResultEvaluation(
            False,
            f"requested range {requested_hours}h but tool output covered {actual_hours:.1f}h",
            result_contract,
            actual,
            "registered_tool_parameter_gap",
        )
    return ResultEvaluation(True, "TimesCar query output satisfies requested range", result_contract, actual)


def is_range_correction(text: str) -> bool:
    return bool(requested_timescar_query_hours(text) is not None)


def recent_tool_from_invocation_log(path: Path | None = None) -> str | None:
    target = path or Path(os.environ.get("OPENCLAW_HARNESS_TOOL_INVOCATION_LOG", "")) if os.environ.get("OPENCLAW_HARNESS_TOOL_INVOCATION_LOG") else WORKSPACE / "var" / "harness_tool_invocations.jsonl"
    if not target.is_file():
        return None
    try:
        lines = target.read_text(encoding="utf-8").splitlines()[-20:]
    except OSError:
        return None
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        tool_id = str(payload.get("tool_id") or "")
        if tool_id:
            return tool_id
    return None


def resolve_correction_tool_id(text: str, context: str = "") -> str | None:
    if not is_range_correction(text):
        return None
    combined = f"{context}\n{text}"
    if "timescar.dm.query" in combined or TIMESCAR_QUERY_CONTEXT_PATTERN.search(combined):
        return "timescar.dm.query"
    recent_tool = recent_tool_from_invocation_log()
    if recent_tool == "timescar.dm.query":
        return recent_tool
    return None
