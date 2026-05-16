#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from model_fallback_client import (
    chat_with_fallback,
    load_runtime_env_files,
    resolve_primary_chat_endpoint,
)
from harness_contracts import contract_prompt, intent_contract_prompt

WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")
REPO = Path(__file__).resolve().parents[2]
RUNTIME_ENV_FILES = (
    Path("/etc/openclaw/openclaw.env"),
    Path("/var/lib/openclaw/.openclaw/openclaw.env"),
)
CONVERSATION_MODES = {"chat", "task", "clarification", "gap"}
DOMAINS = {"timescar", "weather", "news", "cron", "config", "web", "memory", "self", "artifact", "general", "unknown"}
ACTIONS = {"query", "book", "cancel", "status", "adjust", "run", "research", "backfill", "quality", "clean", "list", "retry", "access", "share", "update", "edit", "chat", "gap"}
SAFETY_CLASSES = {"readonly", "write", "credential", "destructive", "ambiguous"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class IntentFrame:
    conversation_mode: str
    domain: str
    action: str
    canonical_text: str
    context_refs: list[dict[str, Any]]
    parameters: dict[str, Any]
    safety: str
    result_contract: dict[str, Any]
    tool_candidates: list[dict[str, Any]]
    confidence: float
    reason: str
    source: str = "model"
    created_at: str = field(default_factory=utc_now)


def model_call_log_path() -> Path:
    configured = os.environ.get("OPENCLAW_HARNESS_MODEL_CALL_LOG", "").strip()
    return Path(configured) if configured else WORKSPACE / "var" / "harness_model_calls.jsonl"


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def intent_model_config() -> tuple[str, str, str]:
    endpoint = resolve_primary_chat_endpoint()
    return endpoint.base_url, endpoint.api_key, endpoint.model


def intent_model_fallback_configs() -> list[tuple[str, str, str]]:
    """Return ordered list of (base_url, api_key, model) fallbacks for the intent agent.

    Falls back to OPENCLAW_OLLAMA_BASE_URL with confirmed-available models when the
    primary codex endpoint returns HTTP 429 (quota exhausted) or is unreachable.
    """
    load_runtime_env_files()
    ollama_base = (
        os.environ.get("OPENCLAW_OLLAMA_BASE_URL", "").strip()
        or "http://ccnode.briconbric.com:22545"
    ).rstrip("/") + "/v1"
    fallback_models_raw = os.environ.get(
        "OPENCLAW_INTENT_FALLBACK_MODELS", "qwen3:14b,qwen2.5:14b-instruct"
    ).strip()
    fallback_models = [m.strip() for m in fallback_models_raw.split(",") if m.strip()]
    return [(ollama_base, "ollama-local", m) for m in fallback_models]


def http_post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc
    return json.loads(raw)


def extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"model did not return JSON: {raw[:200]}")
    data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("model returned non-object JSON")
    return data


def call_model(messages: list[dict[str, str]], *, timeout: int = 30, temperature: float = 0) -> tuple[str, dict[str, Any]]:
    return chat_with_fallback(messages, timeout=timeout, temperature=temperature)


def registry_prompt(registry: dict[str, Any]) -> str:
    return contract_prompt(registry)


def build_prompt(text: str, context: str, registry: dict[str, Any]) -> list[dict[str, str]]:
    system = (
        "You are OpenClaw Harness intentAgent. You are the primary semantic decision maker. "
        "Return strict JSON only. Do not let registry hints replace semantic understanding. "
        "Schema: {conversation_mode, domain, action, canonical_text, context_refs, parameters, safety, result_contract, tool_candidates, confidence, reason}. "
        "conversation_mode: chat|task|clarification|gap. "
        "domain: timescar|weather|news|cron|config|web|memory|self|artifact|general|unknown. "
        "action: query|book|cancel|status|adjust|run|research|backfill|quality|clean|list|retry|access|share|update|edit|chat|gap. "
        "safety: readonly|write|credential|destructive|ambiguous. "
        "tool_candidates is an ordered list of {tool_id, confidence, reason}; only use registered tools from ToolContracts. "
        "Choose by semantic fit to ToolContract.goal/use_when/do_not_use_when/input_contract/output_contract/safety. "
        "Never choose by business keyword matching, pattern hits, or topic words alone. "
        "If the user asks for public rules, policy, pricing, opening hours, current status, latest facts, or external knowledge about any business domain, choose domain=web action=research with openclaw.web.research unless a more specific registered read-only tool can answer directly. "
        "Use gap only when no registered tool can plausibly answer or the request is unsafe/ambiguous; do not use gap merely because the topic name belongs to another domain. "
        "Operational tools such as TimesCar query/book/cancel/adjust are for concrete reservations, not public policy knowledge. "
        "For follow-ups, infer the complete intent from context and write it in canonical_text. "
        "For time ranges, output duration_hours, offset_hours, relation. "
        "Example: 未来一个月 means duration_hours=720 offset_hours=0 relation=within. "
        "Example: 未来一个月以后 means duration_hours=720 offset_hours=720 relation=after. "
        "Example: 帮我查一下 XXX 最新情况 means domain=web action=research and tool candidate openclaw.web.research. "
        "Example: 把之前小红书投稿相关记录回填到长记忆 means domain=memory action=backfill and tool candidate memory.backfill.xhs. "
        "Example: 检查长记忆质量 means domain=memory action=quality and tool candidate memory.curator.xhs. "
        "Example: 清理小红书长记忆噪声 means domain=memory action=clean and tool candidate memory.curator.xhs. "
        "Example: 检查自演进状态 means domain=self action=status and tool candidate openclaw.self_evolution.status. "
        "Example: 我打不开刚才生成的 Google Docs，请给我查看权限 means domain=artifact action=access and tool candidate openclaw.artifact.access_followup; do not answer with task status. "
        "Example: 给刚才那个文档开查看权限 means domain=artifact action=share and tool candidate openclaw.artifact.access_followup. "
        "Example: 给刚才那个文档补充三张图片并更新内容 means domain=artifact action=update and tool candidate openclaw.artifact.update_followup; do not create a missing-tool gap. "
        "Example: 修改刚才交付的文件 means domain=artifact action=edit and tool candidate openclaw.artifact.update_followup. "
        "Example: 我订的车可以提前多久订 means public service policy research, so domain=web action=research, not timescar gap. "
        "Example: 这个链接说了什么 means domain=web action=research and include the URL in parameters. "
        "Example: 现在某服务是否宕机 means domain=web action=research and require current public sources. "
        "If the user asks normal conversation, set conversation_mode=chat and no tool candidates. "
        "For chat mode, canonical_text must be the exact natural user-facing reply, not an analysis of the user's intent. "
        "For liveness greetings such as '还活着吗', reply briefly, e.g. '在。'. "
        "For short follow-ups such as '未来一个月以后的呢？', inspect Recent tool invocations in context; if the last task was a TimesCar query, inherit domain=timescar action=query and produce a complete canonical_text. "
        "For TimesCar follow-ups like '把这单的开始时间往后推24小时，结束时间不变', choose domain=timescar action=adjust, safety=write, and tool candidate timescar.dm.adjust_start. "
        "For TimesCar follow-ups like '把马上开始的那单预订往后整体延15分钟', choose domain=timescar action=adjust, safety=write, and tool candidate timescar.dm.shift_window. "
        "For recurring task status such as '检查每3天一次的小红书文章撰写任务状态', choose domain=cron action=status and tool candidate openclaw.cron.status. "
        "If model cannot safely bind a task, set conversation_mode=clarification or gap."
    )
    user = "\n".join(
        [
            "Intent capability families:",
            intent_contract_prompt(registry),
            "Registered ToolContracts:",
            registry_prompt(registry),
            "Context:",
            context or "(none)",
            "Current message:",
            text,
        ]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def validate_intent_frame(data: dict[str, Any]) -> IntentFrame:
    parameters = data.get("parameters") if isinstance(data.get("parameters"), dict) else {}
    time_range = parameters.get("time_range")
    if isinstance(time_range, dict):
        for key in ("duration_hours", "offset_hours", "relation"):
            if key in time_range and key not in parameters:
                parameters[key] = time_range[key]
    frame = IntentFrame(
        conversation_mode=str(data.get("conversation_mode") or "gap"),
        domain=str(data.get("domain") or "unknown"),
        action=str(data.get("action") or "gap"),
        canonical_text=str(data.get("canonical_text") or ""),
        context_refs=data.get("context_refs") if isinstance(data.get("context_refs"), list) else [],
        parameters=parameters,
        safety=str(data.get("safety") or "ambiguous"),
        result_contract=data.get("result_contract") if isinstance(data.get("result_contract"), dict) else {},
        tool_candidates=data.get("tool_candidates") if isinstance(data.get("tool_candidates"), list) else [],
        confidence=float(data.get("confidence") or 0.0),
        reason=str(data.get("reason") or "model intent frame"),
    )
    if frame.conversation_mode not in CONVERSATION_MODES:
        raise ValueError(f"invalid conversation_mode: {frame.conversation_mode}")
    if frame.domain not in DOMAINS:
        raise ValueError(f"invalid domain: {frame.domain}")
    if frame.action not in ACTIONS:
        raise ValueError(f"invalid action: {frame.action}")
    if frame.safety not in SAFETY_CLASSES:
        raise ValueError(f"invalid safety: {frame.safety}")
    if frame.conversation_mode == "task" and not frame.canonical_text:
        raise ValueError("task intent frame requires canonical_text")
    return frame


def infer_intent_frame(
    text: str,
    *,
    context: str,
    registry: dict[str, Any],
    timeout: int = 30,
    model_caller: Callable[[list[dict[str, str]]], str] | None = None,
) -> IntentFrame:
    messages = build_prompt(text, context, registry)
    meta: dict[str, Any] = {}
    try:
        if model_caller:
            content = model_caller(messages)
            meta = {"model": "test-injected", "latency_ms": 0}
        else:
            content, meta = call_model(messages, timeout=timeout, temperature=0)
        frame = validate_intent_frame(extract_json_object(content))
        append_jsonl(
            model_call_log_path(),
            {
                "created_at": utc_now(),
                "kind": "intent_frame",
                "ok": True,
                "model": meta.get("model"),
                "latency_ms": meta.get("latency_ms"),
                "text": text,
                "frame": asdict(frame),
            },
        )
        return frame
    except Exception as exc:
        append_jsonl(
            model_call_log_path(),
            {
                "created_at": utc_now(),
                "kind": "intent_frame",
                "ok": False,
                "text": text,
                "error": f"{type(exc).__name__}: {exc}",
                "model": meta.get("model"),
            },
        )
        raise
