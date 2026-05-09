#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")
URL_RE = re.compile(r"https?://[^\s<>()\]\"']+", re.IGNORECASE)
WEB_EVIDENCE_RE = re.compile(r"^检索证据：.*$", re.MULTILINE)
DIAGNOSTIC_LINE_RE = re.compile(
    r"^(记录|自演进|自演进状态|重放判定|工具匠|事件日志|诊断|trace_id|kernel_session|gap_id|plan_log)：?.*$",
    re.IGNORECASE,
)
DIAGNOSTIC_TOKEN_RE = re.compile(r"(kernel_session=|gap_id=|plan_log=|trace_id=|/var/lib/openclaw|/tmp/openclaw|capability_gap_events\.jsonl)")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ReportEnvelope:
    task_id: str
    trace_id: str
    status: str
    visibility: str
    summary: str
    diagnostics_ref: str
    public_payload: str = ""
    stage: str = ""
    tool_id: str = ""
    worker_agent: str = ""
    write_operation: bool = False
    postcheck: str = "not_applicable"
    failure_type: str = ""
    allow_links: bool = False
    log_refs: dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)


def report_log_path() -> Path:
    configured = os.environ.get("OPENCLAW_HARNESS_REPORT_LOG", "").strip()
    return Path(configured) if configured else WORKSPACE / "var" / "harness_reports.jsonl"


def append_report(envelope: ReportEnvelope, path: Path | None = None) -> Path:
    target = path or report_log_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(envelope), ensure_ascii=False, sort_keys=True) + "\n")
    return target


def diagnostics_ref(*, trace_id: str, route_kind: str = "", extra: str = "") -> str:
    parts = [f"trace_id={trace_id}"]
    if route_kind:
        parts.append(f"route={route_kind}")
    if extra:
        parts.append(extra)
    return " ".join(parts)


def postcheck_label(tool: dict[str, Any] | None) -> str:
    if not tool or not tool.get("write_operation"):
        return "not_applicable"
    return str(tool.get("postcheck_contract") or tool.get("idempotency") or "missing_postcheck_contract")


def build_report(
    *,
    task_id: str,
    trace_id: str,
    status: str,
    stage: str,
    summary: str,
    route_kind: str,
    tool: dict[str, Any] | None = None,
    visibility: str = "owner_dm",
    public_payload: str = "",
    failure_type: str = "",
    allow_links: bool = False,
    log_refs: dict[str, str] | None = None,
) -> ReportEnvelope:
    return ReportEnvelope(
        task_id=task_id,
        trace_id=trace_id,
        status=status,
        visibility=visibility,
        summary=summary.strip() or status,
        diagnostics_ref=diagnostics_ref(trace_id=trace_id, route_kind=route_kind),
        public_payload=public_payload.strip(),
        stage=stage,
        tool_id=str((tool or {}).get("tool_id") or ""),
        worker_agent=str((tool or {}).get("worker_agent") or (tool or {}).get("owner_agent") or ""),
        write_operation=bool((tool or {}).get("write_operation")),
        postcheck=postcheck_label(tool),
        failure_type=failure_type,
        allow_links=allow_links,
        log_refs=log_refs or {},
    )


def suppress_links(text: str) -> str:
    cleaned = URL_RE.sub("[链接已记录后台]", text or "")
    cleaned = re.sub(r"(?:\s*-\s*)?\[链接已记录后台\]", " [链接已记录后台]", cleaned)
    return cleaned.strip()


def concise_web_research_summary(text: str) -> str:
    raw = WEB_EVIDENCE_RE.sub("", text or "")
    source_index = raw.find("\n来源：")
    if source_index >= 0:
        raw = raw[:source_index]
    raw = raw.replace("联网检索结果\n状态：成功\n", "").replace("联网检索结果\r\n状态：成功\r\n", "")
    lines = [line.rstrip() for line in raw.splitlines()]
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        kept.append(stripped)
        if len(kept) >= 3:
            break
    return "\n".join(kept).strip() or "检索完成，但没有可展示的结论。"


def display_summary(envelope: ReportEnvelope) -> str:
    summary = envelope.summary
    if envelope.tool_id == "openclaw.web.research" and envelope.status == "ok":
        summary = concise_web_research_summary(summary)
    summary = concise_operational_summary(summary)
    if not envelope.allow_links:
        summary = suppress_links(summary)
    return summary


def concise_operational_summary(text: str, *, max_lines: int = 5, max_chars: int = 700) -> str:
    kept: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == "自演进：已修复并重试。":
            kept.append(line)
            continue
        if DIAGNOSTIC_LINE_RE.match(line) or DIAGNOSTIC_TOKEN_RE.search(line):
            continue
        if line.startswith("{") or line.startswith("}") or line.startswith('"'):
            continue
        kept.append(line)
        if len(kept) >= max_lines:
            break
    summary = "\n".join(kept).strip() or "任务已处理，详细诊断已记录后台。"
    if len(summary) > max_chars:
        summary = summary[: max_chars - 1].rstrip() + "…"
    return summary


def status_label(status: str) -> str:
    return {
        "ok": "成功",
        "chat": "回复",
        "failed": "失败",
        "unsupported": "未执行",
    }.get(status, status or "unknown")


def format_owner_reply(envelope: ReportEnvelope) -> str:
    summary = display_summary(envelope)
    if envelope.status == "chat":
        return summary
    lines = [summary, f"状态：{status_label(envelope.status)}"]
    if envelope.write_operation and envelope.status != "ok":
        lines.append("写操作：未执行")
    lines.append("详细诊断：后台日志保留，不投递到公共频道。")
    return "\n".join(item for item in lines if item).strip()
