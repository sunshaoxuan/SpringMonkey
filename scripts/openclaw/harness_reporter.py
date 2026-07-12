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
    summary = structured_tool_summary(summary)
    if envelope.tool_id == "openclaw.web.research" and envelope.status == "ok":
        summary = concise_web_research_summary(summary)
    summary = concise_operational_summary(summary)
    if not envelope.allow_links:
        summary = suppress_links(summary)
    return summary


def structured_tool_summary(text: str) -> str:
    raw = (text or "").strip()
    if not raw.startswith(("{", "[")):
        return text
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return text
    if isinstance(payload, list):
        extracted = extract_presentable_text(payload)
        return "\n".join(extracted) if extracted else text
    if not isinstance(payload, dict):
        return text
    result = str(payload.get("result") or payload.get("final_report") or "").strip()
    tool_id = str(payload.get("tool_id") or "")
    status = str(payload.get("status") or "").strip()
    if status == "error":
        code = str(payload.get("error_code") or "TOOL_ERROR")
        action = str(payload.get("suggested_next_action") or "请稍后重试或查看后台诊断。")
        return f"工具执行失败：{code}\n下一步：{action}"
    if tool_id.startswith("openclaw.generated.") or "自演进状态" in result:
        return summarize_self_evolution_result(result, tool_status=status)
    if result:
        return result
    extracted = extract_presentable_text(payload)
    return "\n".join(extracted) if extracted else text


def extract_presentable_text(payload: Any, *, limit: int = 20) -> list[str]:
    preferred_keys = ("result", "final_report", "output", "stdout", "text", "content", "message", "value")
    ignored_keys = {
        "trace_id",
        "diagnostics_ref",
        "stderr",
        "command",
        "log_refs",
        "textSignature",
    }
    collected: list[str] = []

    def visit(value: Any) -> None:
        if len(collected) >= limit:
            return
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned and cleaned not in collected:
                collected.append(cleaned)
            return
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        for key in preferred_keys:
            if key in value:
                visit(value[key])
        for key, item in value.items():
            if key in preferred_keys or key in ignored_keys:
                continue
            if isinstance(item, (dict, list)):
                visit(item)

    visit(payload)
    return collected


def summarize_self_evolution_result(result: str, *, tool_status: str = "") -> str:
    helper_match = re.search(r"已推广 helper：\s*(\d+)", result or "")
    unresolved_match = re.search(r"未解决缺口：\s*(\d+)", result or "")
    promoted = bool(re.search(r"status=promoted|lifecycle=.*promoted|已推广 helper：\s*[1-9]", result or ""))
    generated = "status=generated" in (result or "")
    blocked = "status=blocked" in (result or "")

    if promoted:
        first = "自演进处理完成：内部只读修复已验证并登记。"
    elif generated:
        first = "自演进已生成修复包，但还没有提升为可用能力。"
    elif blocked:
        first = "自演进已识别阻断，需要授权或补充条件后才能继续。"
    elif tool_status == "success":
        first = "自演进状态检查完成。"
    else:
        first = "自演进处理已有结果。"

    details: list[str] = []
    if helper_match:
        details.append(f"已推广 helper：{helper_match.group(1)}")
    if unresolved_match:
        details.append(f"未解决缺口：{unresolved_match.group(1)}")
    second = "；".join(details)
    if second:
        second += "。"
    next_step = "下一步：可以直接重试原任务；若仍失败，汤猴应沿同一缺口继续收紧。"
    return "\n".join(line for line in [first, second, next_step] if line)


def concise_operational_summary(text: str, *, max_lines: int = 5, max_chars: int = 700) -> str:
    if (text or "").lstrip().startswith("OpenClaw 定时任务状态"):
        max_lines = max(max_lines, 40)
        max_chars = max(max_chars, 1800)
    kept: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == "自演进：已修复并重试。":
            kept.append(line)
            continue
        if line.startswith(("自演进处理完成", "自演进已生成修复包", "自演进已识别阻断", "自演进状态检查完成")):
            kept.append(line)
            continue
        if DIAGNOSTIC_LINE_RE.match(line) or DIAGNOSTIC_TOKEN_RE.search(line):
            continue
        if line.startswith("{") or line.startswith("}") or line.startswith('"'):
            continue
        if re.fullmatch(r"[\[\]{},]+", line):
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
        "tracking": "已启动",
        "failed": "失败",
        "unsupported": "未执行",
    }.get(status, status or "unknown")


def should_use_conversational_success(envelope: ReportEnvelope) -> bool:
    if envelope.status != "ok":
        return False
    if envelope.write_operation or envelope.failure_type:
        return False
    if envelope.visibility not in {"owner_dm", "dm", "private"}:
        return False
    return True


def format_owner_reply(envelope: ReportEnvelope) -> str:
    summary = display_summary(envelope)
    if envelope.status == "chat":
        return summary
    if should_use_conversational_success(envelope):
        return "\n".join(item for item in [summary, "---"] if item).strip()
    lines = [summary, f"触发状态：{status_label(envelope.status)}"]
    if envelope.write_operation and envelope.status != "ok":
        lines.append("写操作：未执行")
    lines.append("详细诊断：后台日志保留，不投递到公共频道。")
    lines.append("---")
    return "\n".join(item for item in lines if item).strip()
