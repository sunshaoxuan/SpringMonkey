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
    ChatEndpoint,
    MAX_FALLBACK_TIMEOUT_SECONDS,
    chat_with_fallback,
    load_runtime_env_files,
    read_fallback_secret_env,
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
ACTIONS = {
    "query",
    "book",
    "cancel",
    "status",
    "adjust",
    "run",
    "research",
    "backfill",
    "quality",
    "clean",
    "list",
    "retry",
    "access",
    "share",
    "update",
    "edit",
    "repair",
    "implement",
    "verify",
    "push",
    "chat",
    "gap",
}
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

    No fallback is configured by default. A fallback must be explicitly supplied
    through OPENCLAW_INTENT_FALLBACK_BASE_URL and OPENCLAW_INTENT_FALLBACK_MODELS.
    """
    load_runtime_env_files()
    base = os.environ.get("OPENCLAW_INTENT_FALLBACK_BASE_URL", "").strip().rstrip("/")
    fallback_models_raw = os.environ.get("OPENCLAW_INTENT_FALLBACK_MODELS", "").strip()
    if not base or not fallback_models_raw:
        return []
    fallback_models = [m.strip() for m in fallback_models_raw.split(",") if m.strip()]
    api_key = read_fallback_secret_env("OPENCLAW_INTENT_FALLBACK_API_KEY")
    return [(base, api_key, m) for m in fallback_models]


def intent_model_fallback_timeout(primary_timeout: int) -> int:
    load_runtime_env_files()
    raw = os.environ.get("OPENCLAW_INTENT_FALLBACK_TIMEOUT_SECONDS", "180").strip()
    try:
        configured = int(raw)
    except ValueError:
        configured = 180
    return max(1, min(max(configured, primary_timeout), MAX_FALLBACK_TIMEOUT_SECONDS))


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
    if start < 0:
        raise ValueError(f"model did not return JSON: {raw[:200]}")
    try:
        data, _end = json.JSONDecoder().raw_decode(raw[start:])
    except ValueError as exc:
        raise ValueError(f"model did not return a JSON object: {raw[:200]}") from exc
    if not isinstance(data, dict):
        raise ValueError("model returned non-object JSON")
    return data


def call_model(messages: list[dict[str, str]], *, timeout: int = 30, temperature: float = 0) -> tuple[str, dict[str, Any]]:
    return chat_with_fallback(messages, timeout=timeout, temperature=temperature, allow_fallback=False)


def registry_prompt(registry: dict[str, Any]) -> str:
    return contract_prompt(registry)


def build_prompt(text: str, context: str, registry: dict[str, Any]) -> list[dict[str, str]]:
    system = (
        "You are OpenClaw Harness intentAgent. You are the primary semantic decision maker. "
        "Return strict JSON only. Do not let registry hints replace semantic understanding. "
        "Schema: {conversation_mode, domain, action, canonical_text, context_refs, parameters, safety, result_contract, tool_candidates, confidence, reason}. "
        "context_refs and tool_candidates must be JSON arrays. parameters and result_contract must be JSON objects; use [] or {} when empty and never use null or a string for these fields. "
        "conversation_mode: chat|task|clarification|gap. "
        "domain: timescar|weather|news|cron|config|web|memory|self|artifact|general|unknown. "
        "action: query|book|cancel|status|adjust|run|research|backfill|quality|clean|list|retry|access|share|update|edit|repair|implement|verify|push|chat|gap. "
        "safety: readonly|write|credential|destructive|ambiguous. "
        "tool_candidates is an ordered list of {tool_id, confidence, reason}; only use registered tools from ToolContracts. "
        "Choose by semantic fit to ToolContract.goal/use_when/do_not_use_when/input_contract/output_contract/safety. "
        "Never choose by business keyword matching, pattern hits, or topic words alone. "
        "If the user asks for public rules, policy, pricing, opening hours, current status, latest facts, or external knowledge about any business domain, choose domain=web action=research with openclaw.web.research unless a more specific registered read-only tool can answer directly. "
        "Use gap only when no registered tool can plausibly answer or the request is unsafe/ambiguous; do not use gap merely because the topic name belongs to another domain. "
        "When one user request contains both autonomous internal self-improvement work and a later external/public side effect, split the boundary semantically: "
        "the internal implementation, repository changes, tests, registry updates, private-channel verification, and git push are an owner-controlled self-improvement gap; "
        "the later public-channel replacement, public posting, third-party write, credential/2FA, payment, deletion, or privacy exposure remains approval-gated. "
        "Do not reject the whole request as boundary-unclear. Set conversation_mode=gap, domain=self or config, safety=write, and describe the executable internal portion plus the held external approval gate in parameters/result_contract. "
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
        "For questions about whether a scheduled recurring job exists, is enabled, where it publishes, or why it appears stopped, choose domain=cron action=status and tool candidate openclaw.cron.status; infer parameters.topic semantically from the job family, and do not run the job. "
        "Example: 继续补齐刚才失败的内部自增益能力 means domain=self action=repair and tool candidate openclaw.self_evolution.internal_repair. "
        "Example: 执行通用能力补齐 run 并验证后推仓库 means domain=self action=repair or action=implement and tool candidate openclaw.self_evolution.internal_repair. "
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


REQUIRED_INTENT_FRAME_KEYS = {
    "conversation_mode",
    "domain",
    "action",
    "canonical_text",
    "context_refs",
    "parameters",
    "safety",
    "result_contract",
    "tool_candidates",
    "confidence",
    "reason",
}


def validate_intent_frame(data: dict[str, Any]) -> IntentFrame:
    missing = sorted(REQUIRED_INTENT_FRAME_KEYS.difference(data))
    if missing:
        raise ValueError(f"intent frame missing required keys: {missing}")
    context_refs = [] if data["context_refs"] is None else data["context_refs"]
    parameters = {} if data["parameters"] is None else data["parameters"]
    result_contract = {} if data["result_contract"] is None else data["result_contract"]
    raw_tool_candidates = [] if data["tool_candidates"] is None else data["tool_candidates"]
    if not isinstance(context_refs, list):
        raise ValueError("context_refs must be a list")
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be an object")
    if not isinstance(result_contract, dict):
        raise ValueError("result_contract must be an object")
    if not isinstance(raw_tool_candidates, list):
        raise ValueError("tool_candidates must be a list")
    tool_candidates: list[dict[str, Any]] = []
    for candidate in raw_tool_candidates:
        if not isinstance(candidate, dict) or not str(candidate.get("tool_id") or "").strip():
            raise ValueError("tool_candidates entries require a non-empty tool_id")
        try:
            candidate_confidence = float(candidate.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise ValueError("tool_candidates entries require numeric confidence") from exc
        if not 0 <= candidate_confidence <= 1:
            raise ValueError("tool candidate confidence must be between 0 and 1")
        normalized = dict(candidate)
        normalized["tool_id"] = str(candidate["tool_id"]).strip()
        normalized["confidence"] = candidate_confidence
        normalized["reason"] = str(candidate.get("reason") or "")
        tool_candidates.append(normalized)
    try:
        confidence = float(data["confidence"])
    except (TypeError, ValueError) as exc:
        raise ValueError("intent frame confidence must be numeric") from exc
    if not 0 <= confidence <= 1:
        raise ValueError("intent frame confidence must be between 0 and 1")
    time_range = parameters.get("time_range")
    if isinstance(time_range, dict):
        for key in ("duration_hours", "offset_hours", "relation"):
            if key in time_range and key not in parameters:
                parameters[key] = time_range[key]
    frame = IntentFrame(
        conversation_mode=str(data["conversation_mode"]).strip(),
        domain=str(data["domain"]).strip(),
        action=str(data["action"]).strip(),
        canonical_text=str(data["canonical_text"] or ""),
        context_refs=context_refs,
        parameters=parameters,
        safety=str(data["safety"]).strip(),
        result_contract=result_contract,
        tool_candidates=tool_candidates,
        confidence=confidence,
        reason=str(data["reason"] or "model intent frame"),
    )
    if frame.conversation_mode not in CONVERSATION_MODES:
        raise ValueError(f"invalid conversation_mode: {frame.conversation_mode}")
    if frame.domain not in DOMAINS:
        raise ValueError(f"invalid domain: {frame.domain}")
    if frame.action not in ACTIONS:
        raise ValueError(f"invalid action: {frame.action}")
    if frame.safety not in SAFETY_CLASSES:
        raise ValueError(f"invalid safety: {frame.safety}")
    if frame.conversation_mode in {"task", "chat"} and not frame.canonical_text.strip():
        raise ValueError(f"{frame.conversation_mode} intent frame requires canonical_text")
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
    attempts: list[dict[str, str]] = []
    try:
        if model_caller:
            content = model_caller(messages)
            meta = {"model": "test-injected", "latency_ms": 0}
            frame = validate_intent_frame(extract_json_object(content))
        else:
            try:
                content, meta = call_model(messages, timeout=timeout, temperature=0)
                frame = validate_intent_frame(extract_json_object(content))
            except Exception as primary_exc:
                attempts.append(
                    {
                        "model": str(meta.get("model") or "primary"),
                        "error": f"{type(primary_exc).__name__}: {primary_exc}",
                    }
                )
                fallback_timeout = intent_model_fallback_timeout(timeout)
                fallback_deadline = time.monotonic() + MAX_FALLBACK_TIMEOUT_SECONDS
                fallback_errors: list[str] = []
                for base_url, api_key, model in intent_model_fallback_configs():
                    remaining = fallback_deadline - time.monotonic()
                    if remaining <= 0:
                        attempts.append({"model": model, "error": "intent fallback budget exhausted"})
                        fallback_errors.append(f"{model}: intent fallback budget exhausted")
                        break
                    try:
                        endpoint = ChatEndpoint("openai_compatible", base_url, model, api_key)
                        content, meta = chat_with_fallback(
                            messages,
                            timeout=max(1, min(fallback_timeout, int(remaining))),
                            temperature=0,
                            primary=endpoint,
                            fallback=None,
                            allow_fallback=False,
                        )
                        frame = validate_intent_frame(extract_json_object(content))
                        meta["fallback_used"] = True
                        meta["intent_fallback"] = True
                        break
                    except Exception as fallback_exc:
                        detail = f"{type(fallback_exc).__name__}: {fallback_exc}"
                        fallback_errors.append(f"{model}: {detail}")
                        attempts.append({"model": model, "error": detail})
                else:
                    details = "; ".join(fallback_errors) or "no explicit intent fallback configured"
                    raise RuntimeError(f"intent model candidates exhausted: {details}") from primary_exc
        append_jsonl(
            model_call_log_path(),
            {
                "created_at": utc_now(),
                "kind": "intent_frame",
                "ok": True,
                "model": meta.get("model"),
                "latency_ms": meta.get("latency_ms"),
                "fallback_used": bool(meta.get("fallback_used")),
                "attempts": attempts,
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
                "attempts": attempts,
            },
        )
        raise
