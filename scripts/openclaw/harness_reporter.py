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


def format_owner_reply(envelope: ReportEnvelope) -> str:
    summary = envelope.summary if envelope.allow_links else suppress_links(envelope.summary)
    if envelope.status == "chat":
        return summary
    lines = [summary]
    meta = [
        f"任务：{envelope.task_id}",
        f"阶段：{envelope.stage or 'unknown'}",
        f"工具：{envelope.tool_id or 'none'}",
        f"写操作：{'是' if envelope.write_operation else '否'}",
        f"回查：{envelope.postcheck}",
    ]
    if envelope.failure_type:
        meta.append(f"失败类型：{envelope.failure_type}")
    meta.append(f"诊断：{envelope.diagnostics_ref}")
    lines.append("\n".join(meta))
    return "\n".join(item for item in lines if item).strip()
