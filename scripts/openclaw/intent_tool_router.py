#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = REPO / "config" / "openclaw" / "intent_tools.json"
DEFAULT_KERNEL_ROOT = Path("/var/lib/openclaw/.openclaw/workspace/agent_society_kernel")
RUNTIME_ENV_FILES = (
    Path("/etc/openclaw/openclaw.env"),
    Path("/var/lib/openclaw/.openclaw/openclaw.env"),
)
DEFAULT_DIAGNOSTIC_LOG = Path("/var/lib/openclaw/.openclaw/workspace/var/intent_tool_router_diagnostics.jsonl")

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from dm_capability_gap_runner import run_gap
from harness_dispatcher import handle_event
from harness_governance import evaluate_tool_invocation
from harness_intent_agent import infer_intent_frame
from harness_intent_audit import audit_intent, evaluate_result, resolve_correction_tool_id
from harness_intent_completion import complete_implicit_intent
from harness_observability import EvaluationRecord, ToolInvocationRecord, record_evaluation, record_tool_invocation
from harness_runtime import make_id
from harness_semantic_reviewer import review_intent_frame
from harness_tool_binder import bind_tool

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


@dataclass
class Classification:
    intent_id: str | None
    tool_id: str | None
    confidence: float
    reason: str
    tool: dict[str, Any] | None = None
    intent_frame: dict[str, Any] | None = None


@dataclass
class RouterResult:
    status: str
    reply: str
    classification: Classification
    args: dict[str, Any]
    returncode: int = 0
    route_kind: str = "unknown"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "").strip()


CHAT_ONLY_PATTERN = re.compile(
    r"^\s*(你好|您好|hi|hello|早上好|晚上好|谢谢|thanks|ok|好的|收到|嗯|在吗|还活着吗|你还活着吗|拜拜|bye)[!！,.，。 ]*\s*$",
    re.IGNORECASE,
)

TASK_VERB_PATTERN = re.compile(
    r"(请|帮|麻烦|需要|处理|执行|完成|安排|调查|排查|修复|检查|查询|查看|触发|重跑|补跑|取消|修改|调整|设置|部署|重启|创建|生成|发明|新增|接入|汇报|报告|发到|转发)",
    re.IGNORECASE,
)

AUTO_SAFE_READONLY_PATTERN = re.compile(
    r"(天气|天気|weather|预报|予報|风况|風|能见度|視程|可視性|节假日|祝日|红日子|holiday)",
    re.IGNORECASE,
)

UNSAFE_TASK_PATTERN = re.compile(
    r"(取消|修改|改|调整|设置|配置|部署|重启|删除|提交|支付|付款|订车|预约|timescar|密码|token|secret|key|密钥|登录|登入)",
    re.IGNORECASE,
)


def load_runtime_env_files(paths: tuple[Path, ...] = RUNTIME_ENV_FILES) -> None:
    for path in paths:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = value.strip().strip('"').strip("'")


def read_secret_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
        file_value = os.environ.get(f"{name}_FILE", "").strip()
        if file_value:
            try:
                secret = Path(file_value).read_text(encoding="utf-8").strip()
            except OSError:
                secret = ""
            if secret:
                return secret
    return ""


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


def local_classify_unregistered_intent(text: str) -> str:
    normalized_prompt = re.sub(r"\s+", " ", text or "").strip()
    if not normalized_prompt:
        return "chat"
    if CHAT_ONLY_PATTERN.fullmatch(normalized_prompt):
        return "chat"
    if UNSAFE_TASK_PATTERN.search(normalized_prompt):
        return "unsafe_gap"
    if AUTO_SAFE_READONLY_PATTERN.search(normalized_prompt):
        return "auto_safe_readonly_gap"
    # Short messages without an action verb are still chat, not capability gaps.
    if len(normalize_text(normalized_prompt)) <= 12 and not TASK_VERB_PATTERN.search(normalized_prompt):
        return "chat"
    if TASK_VERB_PATTERN.search(normalized_prompt):
        return "ambiguous_gap"
    return "chat"


def intent_model_config() -> tuple[str, str, str]:
    load_runtime_env_files()
    base_url = (
        os.environ.get("OPENCLAW_INTENT_MODEL_BASE_URL", "").strip()
        or os.environ.get("OPENCLAW_PUBLIC_MODEL_BASE_URL", "").strip()
        or os.environ.get("NEWS_CODEX_BASE_URL", "").strip()
    ).rstrip("/")
    api_key = read_secret_env(
        "OPENCLAW_INTENT_MODEL_API_KEY",
        "OPENCLAW_PUBLIC_MODEL_API_KEY",
        "NEWS_CODEX_API_KEY",
        "OPENCLAW_CODEX_API_KEY",
        "CODEX_API_KEY",
    )
    model = (
        os.environ.get("OPENCLAW_INTENT_MODEL", "").strip()
        or os.environ.get("OPENCLAW_PUBLIC_MODEL", "").strip()
        or "gpt-5.5"
    )
    if not base_url:
        raise RuntimeError("missing OPENCLAW_INTENT_MODEL_BASE_URL/OPENCLAW_PUBLIC_MODEL_BASE_URL")
    return base_url, api_key, model


def call_intent_model(messages: list[dict[str, str]], *, timeout: int, temperature: float = 0) -> str:
    base_url, api_key, model = intent_model_config()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = http_post_json(base_url + "/chat/completions", payload, headers, timeout)
    return str(data["choices"][0]["message"]["content"]).strip()


def model_classify_unregistered_intent(text: str, *, timeout: int = 8) -> tuple[str, str]:
    system = (
        "You are an intent classifier for a Discord DM control console. "
        "Return strict JSON only. Schema: "
        '{"route_kind":"chat|registered_candidate|auto_safe_readonly_gap|unsafe_gap|ambiguous_gap","confidence":0.0,"reason":"short reason"}. '
        "Use chat for greetings, small talk, opinions, explanations, or normal conversation. "
        "Use registered_candidate when the wording appears to match an existing deterministic OpenClaw capability but was not matched by the registry. "
        "Use auto_safe_readonly_gap for public read-only information queries such as weather, holidays, public facts, or external data lookups. "
        "Use unsafe_gap for write operations, booking changes, credentials, configuration, deployment, payment, login, or state-changing work. "
        "Use ambiguous_gap for tasks that are not clearly safe read-only and not clearly unsafe. "
        "Do not choose a gap kind for casual conversation."
    )
    content = call_intent_model(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        timeout=timeout,
        temperature=0,
    )
    parsed = extract_json_object(str(content))
    route_kind = str(parsed.get("route_kind", "")).strip()
    if route_kind not in {"chat", "registered_candidate", "auto_safe_readonly_gap", "unsafe_gap", "ambiguous_gap"}:
        raise ValueError(f"invalid route_kind from model: {route_kind}")
    reason = str(parsed.get("reason") or "model intent classification").strip()
    return route_kind, reason


def registry_prompt(registry: dict[str, Any]) -> str:
    tools = []
    for tool in registry.get("tools", []):
        tools.append(
            {
                "intent_id": tool.get("intent_id"),
                "tool_id": tool.get("tool_id"),
                "description": tool.get("description"),
                "patterns": tool.get("patterns", []),
                "required_any": tool.get("required_any", []),
                "write_operation": bool(tool.get("write_operation")),
            }
        )
    return json.dumps(tools, ensure_ascii=False)


def latest_timescar_context() -> str:
    trace_dir = Path("/var/lib/openclaw/.openclaw/workspace/state/timescar_traces")
    if not trace_dir.is_dir():
        return ""
    candidates = sorted(trace_dir.glob("timescar-*.latest.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    snippets: list[str] = []
    for path in candidates[:3]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        final_message = str(data.get("finalMessage") or "").strip()
        if not final_message:
            continue
        snippets.append(f"{path.name}: {final_message[:900]}")
    return "\n".join(snippets)


def effective_context(text: str, context: str) -> str:
    raw = (context or "").strip()
    normalized = normalize_text(text)
    if any(token in normalized for token in ("刚刚", "刚才", "这单", "订单", "预约", "订车", "TimesCar", "timescar")):
        recent = latest_timescar_context()
        if recent:
            raw = "\n".join(item for item in [raw, "Recent TimesCar task summaries:", recent] if item)
    return raw


def model_classify_intent(text: str, registry: dict[str, Any], *, context: str = "", timeout: int = 10) -> tuple[Classification, str]:
    system = (
        "You are a deterministic tool selector for the owner's Discord DM control console. "
        "Return strict JSON only. Schema: "
        '{"route_kind":"chat|registered_task|registered_candidate|auto_safe_readonly_gap|unsafe_gap|ambiguous_gap",'
        '"tool_id":null,"action":"book|cancel|keep|query|status|adjust|chat|gap","confidence":0.0,'
        '"canonical_text":"completed user intent","parameters":{"duration_hours":null,"offset_hours":0,"relation":"within|after|before|exact|unknown"},'
        '"reason":"short reason"}. '
        "First infer action, then choose exactly one registered tool when action is covered. "
        "Always produce canonical_text and semantic parameters for registered_task. "
        "Use registered_task only when one registry tool clearly matches the user's requested action. "
        "Use chat for normal conversation or explanation. "
        "Use auto_safe_readonly_gap for safe public read-only lookups not covered by a tool. "
        "Use unsafe_gap for write operations, bookings, credentials, configuration, deployment, payment, login, or state changes not covered by a tool. "
        "Use ambiguous_gap when the user appears to request a task but intent/tool is unclear. "
        "For TimesCar: booking a car/reservation for tomorrow 09:00-21:00 with the habitual model is the book_window route. "
        "For TimesCar: after a booking attempt says the preferred car/window is unavailable, asking to switch to an available car is also the book_window route. "
        "For TimesCar: asking whether an order was cancelled, whether cancel succeeded, or whether the order still exists is a read-only cancel_status route. "
        "For TimesCar: keep/保留 means record a keep decision. "
        "For TimesCar: cancel this order/取消这单/把刚刚这单取消掉/取消掉 means cancel_next, especially when context has a recent successful booking. "
        "For TimesCar: adjust_start is only for explicit start-time changes, such as moving tomorrow 09:00 to the day after tomorrow 09:00. "
        "For TimesCar query ranges: '未来一个月' means duration_hours 720, offset_hours 0, relation within. "
        "For TimesCar query ranges: '未来一个月以后' or '一个月以后' means duration_hours 720, offset_hours 720, relation after. "
        "For short follow-ups such as '一个月的' or '未来2周的呢', inherit the recent query intent from context and output a complete canonical_text. "
        "Do not select adjust_start merely because the word 取消 appears; '取消明天的时间，让开始时间从后天...' is adjust_start, but '把这单取消掉' is cancel_next. "
        "Examples: "
        "'好的，把刚刚这单取消掉吧' => action cancel, tool_id timescar.dm.cancel_next. "
        "'把这单取消掉' => action cancel, tool_id timescar.dm.cancel_next. "
        "'这单取消了吗' => action status, tool_id timescar.dm.cancel_status. "
        "'请把明天开始的订车改到后天早9点' => action adjust, tool_id timescar.dm.adjust_start. "
        "'取消明天的时间，让开始时间从后天早上9点开始' => action adjust, tool_id timescar.dm.adjust_start."
    )
    user = "\n".join(
        [
            "Registry tools:",
            registry_prompt(registry),
            "Conversation context:",
            effective_context(text, context) or "(not provided)",
            "Current message:",
            text,
        ]
    )
    content = call_intent_model(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        timeout=timeout,
        temperature=0,
    )
    parsed = extract_json_object(content)
    route_kind = str(parsed.get("route_kind", "")).strip()
    if route_kind not in {"chat", "registered_task", "registered_candidate", "auto_safe_readonly_gap", "unsafe_gap", "ambiguous_gap"}:
        raise ValueError(f"invalid route_kind from model: {route_kind}")
    reason = str(parsed.get("reason") or "model first-stage intent routing").strip()
    confidence = float(parsed.get("confidence") or 0.0)
    tool_id = parsed.get("tool_id")
    frame = {
        "source": "model",
        "route_kind": route_kind,
        "tool_id": tool_id,
        "action": parsed.get("action"),
        "canonical_text": parsed.get("canonical_text"),
        "parameters": parsed.get("parameters") if isinstance(parsed.get("parameters"), dict) else {},
        "reason": reason,
        "confidence": confidence,
    }
    if route_kind == "registered_task":
        if not tool_id:
            raise ValueError("registered_task without tool_id")
        tool = next((item for item in registry.get("tools", []) if str(item.get("tool_id")) == str(tool_id)), None)
        if tool is None:
            raise ValueError(f"model selected unknown tool_id: {tool_id}")
        return Classification(str(tool["intent_id"]), str(tool["tool_id"]), confidence, reason, tool, frame), "registered_task"
    return Classification(None, None, confidence, reason, None, frame), route_kind


def _tool_by_id(registry: dict[str, Any], tool_id: str) -> dict[str, Any] | None:
    return next((item for item in registry.get("tools", []) if str(item.get("tool_id")) == tool_id), None)


def looks_like_timescar_cancel(text: str) -> bool:
    normalized = normalize_text(text)
    if "取消明天的时间" in normalized and ("后天" in normalized or "開始" in normalized or "开始" in normalized):
        return False
    if any(token in normalized for token in ("取消了吗", "取消了么", "取消成功", "是否取消", "有没有取消", "还在吗", "还在不在", "状态")):
        return False
    has_target = any(token in normalized for token in ("这单", "刚刚这单", "刚才这单", "订单", "预约", "订车", "TimesCar", "timescar"))
    has_cancel = any(token in normalized for token in ("取消这单", "这单取消", "把这单取消", "刚刚这单取消", "刚才这单取消", "取消掉", "取消订单", "取消预约", "取消订车", "cancel"))
    return has_target and has_cancel


def looks_like_timescar_adjust(text: str) -> bool:
    normalized = normalize_text(text)
    has_timescar = any(token in normalized for token in ("订车", "预约", "TimesCar", "timescar"))
    if not has_timescar:
        return False
    if looks_like_timescar_cancel(normalized):
        return False
    return any(token in normalized for token in ("开始时间", "后天", "延迟", "延期", "变更", "改到", "改成", "结束时间不变")) and any(
        token in normalized for token in ("后天", "开始时间", "早上9点", "早9点", "09", "结束时间不变")
    )


def guard_timescar_classification(text: str, registry: dict[str, Any], classification: Classification) -> Classification:
    if looks_like_timescar_cancel(text) and classification.tool_id != "timescar.dm.cancel_next":
        tool = _tool_by_id(registry, "timescar.dm.cancel_next")
        if tool:
            return Classification(
                str(tool["intent_id"]),
                str(tool["tool_id"]),
                max(classification.confidence, 0.96),
                f"guarded TimesCar cancel intent; model_tool_id={classification.tool_id}; router_reason={classification.reason}",
                tool,
            )
    if classification.tool_id == "timescar.dm.adjust_start" and not looks_like_timescar_adjust(text):
        tool = _tool_by_id(registry, "timescar.dm.cancel_next") if looks_like_timescar_cancel(text) else None
        if tool:
            return Classification(
                str(tool["intent_id"]),
                str(tool["tool_id"]),
                max(classification.confidence, 0.96),
                f"guarded away from adjust_start; model_tool_id={classification.tool_id}; router_reason={classification.reason}",
                tool,
            )
    return classification


def classify_intent_model_first(text: str, channel: str, user_id: str, registry: dict[str, Any], context: str = "") -> tuple[Classification, str | None]:
    try:
        classification, route_kind = model_classify_intent(text, registry, context=context)
        return classification, route_kind
    except Exception as exc:
        return Classification(None, None, 0.0, f"model_first_unavailable={type(exc).__name__}: {exc}"), None


def model_chat_reply(text: str, *, timeout: int = 25) -> str:
    system = (
        "You are Tanghou replying in the owner's Discord DM super-console. "
        "Reply in Chinese unless the user clearly asks for another language. "
        "Be concise and direct. Current date is 2026-05-04, timezone Asia/Tokyo. "
        "If the user is asking you to execute or change system state, do not pretend it was done; "
        "say that it should be routed as a task instead."
    )
    reply = call_intent_model(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        timeout=timeout,
        temperature=0.2,
    )
    return reply or "我收到消息，但聊天模型没有返回内容。"


def classify_unregistered_intent(text: str) -> tuple[str, str]:
    try:
        return model_classify_unregistered_intent(text)
    except Exception as exc:
        route_kind = local_classify_unregistered_intent(text)
        return route_kind, f"model_unavailable_fallback={type(exc).__name__}: {exc}"


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _matches_any(text: str, needles: list[str]) -> list[str]:
    lowered = text.lower()
    return [needle for needle in needles if needle.lower() in lowered]


def classify(text: str, channel: str, user_id: str, registry: dict[str, Any] | None = None) -> Classification:
    registry = registry or load_registry()
    normalized = normalize_text(text)
    best: tuple[float, str, dict[str, Any], list[str]] | None = None
    for tool in registry.get("tools", []):
        patterns = [str(item) for item in tool.get("patterns", [])]
        required_any = [str(item) for item in tool.get("required_any", [])]
        pattern_hits = _matches_any(normalized, patterns)
        required_hits = _matches_any(normalized, required_any)
        if not pattern_hits or (required_any and not required_hits):
            continue
        score = min(0.99, 0.5 + 0.08 * len(pattern_hits) + 0.08 * len(required_hits))
        reason = f"matched patterns={pattern_hits} required={required_hits}"
        if best is None or score > best[0]:
            best = (score, reason, tool, pattern_hits + required_hits)
    if best is None:
        return Classification(None, None, 0.0, "no registered intent matched")
    score, reason, tool, _hits = best
    return Classification(str(tool["intent_id"]), str(tool["tool_id"]), score, reason, tool)


def classification_for_tool_id(registry: dict[str, Any], tool_id: str, reason: str, intent_frame: dict[str, Any] | None = None) -> Classification | None:
    tool = _tool_by_id(registry, tool_id)
    if not tool:
        return None
    return Classification(str(tool["intent_id"]), str(tool["tool_id"]), 0.97, reason, tool, intent_frame)


def parse_message_time(raw: str) -> datetime:
    value = datetime.fromisoformat((raw or utc_now()).replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def extract_cron_job_from_text(text: str, job_map: dict[str, str]) -> str | None:
    normalized = normalize_text(text)
    for key in sorted(job_map, key=len, reverse=True):
        if key in normalized:
            return job_map[key]
    if re.search(r"(17点|17時|1700)", normalized):
        return job_map.get("17") or job_map.get("1700")
    if re.search(r"(9点|09点|9時|09時|0900)", normalized):
        return job_map.get("9") or job_map.get("09") or job_map.get("0900")
    return None


def extract_args(tool: dict[str, Any], text: str, message_timestamp: str) -> dict[str, Any]:
    schema = tool.get("args_schema") or {}
    mode = schema.get("mode")
    if mode == "dm_text_timestamp":
        args = {
            "text": text,
            "message_timestamp": message_timestamp,
            "force": bool(schema.get("force")),
        }
        parse_message_time(message_timestamp)
        return args
    if mode == "cron_job_from_text":
        job_name = extract_cron_job_from_text(text, schema.get("job_map") or {})
        if not job_name:
            raise ValueError("无法从指令中识别正式 cron 任务时间；请明确 09:00 或 17:00")
        return {"job_name": job_name}
    if mode == "fixed_cron_job":
        return {"job_name": str(schema["job_name"])}
    raise ValueError(f"unsupported args_schema mode: {mode}")


def apply_model_intent_frame(args: dict[str, Any], classification: Classification) -> dict[str, Any]:
    frame = classification.intent_frame or {}
    if not frame:
        return args
    updated = dict(args)
    canonical_text = str(frame.get("canonical_text") or "").strip()
    if canonical_text and (classification.tool or {}).get("args_schema", {}).get("mode") == "dm_text_timestamp":
        updated["text"] = canonical_text
    updated["_model_intent_frame"] = frame
    return updated


def diagnostic_log_path() -> Path:
    configured = os.environ.get("OPENCLAW_INTENT_TOOL_DIAG_LOG", "").strip()
    return Path(configured) if configured else DEFAULT_DIAGNOSTIC_LOG


def append_tool_diagnostic(tool: dict[str, Any], args: dict[str, Any], returncode: int, stderr: str) -> None:
    if not stderr.strip():
        return
    path = diagnostic_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "recorded_at": utc_now(),
            "tool_id": tool.get("tool_id"),
            "intent_id": tool.get("intent_id"),
            "returncode": returncode,
            "stderr": stderr[-4000:],
            "args": {key: value for key, value in args.items() if key not in {"text"}},
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Diagnostics must never pollute the user-facing reply path.
        return


def run_tool(tool: dict[str, Any], args: dict[str, Any], timeout_seconds: int) -> tuple[int, str]:
    entrypoint = REPO / str(tool["entrypoint"])
    mode = (tool.get("args_schema") or {}).get("mode")
    if mode == "dm_text_timestamp":
        cmd = [
            sys.executable,
            str(entrypoint),
            "--text",
            args["text"],
            "--message-timestamp",
            args["message_timestamp"],
        ]
        if args.get("force"):
            cmd.append("--force")
    elif mode in {"cron_job_from_text", "fixed_cron_job"}:
        cmd = [sys.executable, str(entrypoint), args["job_name"]]
    else:
        raise ValueError(f"unsupported execution mode: {mode}")
    started = time.monotonic()
    proc = subprocess.run(
        cmd,
        cwd=REPO,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_seconds,
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    append_tool_diagnostic(tool, args, proc.returncode, proc.stderr or "")
    trace_id = str(args.get("_harness_trace_id") or make_id("trace"))
    task_id = str(args.get("_harness_task_id") or make_id("task"))
    record_tool_invocation(
        ToolInvocationRecord(
            trace_id=trace_id,
            task_id=task_id,
            tool_id=str(tool.get("tool_id") or ""),
            owner_agent=str(tool.get("owner_agent") or "toolWorker"),
            status="ok" if proc.returncode == 0 else "failed",
            latency_ms=latency_ms,
            result_summary=(proc.stdout or proc.stderr or "")[:700],
            permission_scope=str(tool.get("permission_scope") or tool.get("permission") or ""),
            input_summary=str(args.get("text") or args.get("job_name") or "")[:700],
            result_contract=json.dumps(args.get("_result_contract") or {}, ensure_ascii=False, sort_keys=True),
        )
    )
    return proc.returncode, (proc.stdout or "").strip()


def format_reply(tool: dict[str, Any], args: dict[str, Any], returncode: int, output: str) -> str:
    reply_policy = tool.get("reply_policy")
    if returncode == 0 and reply_policy == "cron_ack":
        return "\n".join(
            [
                "OpenClaw 正式任务已由汤猴事件入口触发。",
                f"任务：{args.get('job_name')}",
                output or "cron run command completed",
            ]
        )
    prefix = "汤猴事件入口执行成功。" if returncode == 0 else f"汤猴事件入口执行失败，退出码：{returncode}"
    return f"{prefix}\n{output or 'no output'}"


def fallback_gap_path(kernel_root: Path) -> Path:
    return kernel_root / "intent_tool_router_gaps.jsonl"


def record_capability_gap(text: str, channel: str, user_id: str, reason: str, kernel_root: Path) -> str:
    kernel_root.mkdir(parents=True, exist_ok=True)
    fallback = fallback_gap_path(kernel_root)
    record = {
        "recorded_at": utc_now(),
        "channel": channel,
        "user_id": user_id,
        "text": text,
        "reason": reason,
        "status": "open",
        "next_required_change": "add or refine config/openclaw/intent_tools.json and a deterministic tool entrypoint",
    }
    with fallback.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    kernel_script = REPO / "scripts" / "openclaw" / "agent_society_kernel.py"
    try:
        ensure = subprocess.run(
            [
                sys.executable,
                str(kernel_script),
                "--root",
                str(kernel_root),
                "ensure-session",
                "--prompt",
                text,
                "--channel",
                channel,
                "--user-id",
                user_id,
            ],
            cwd=REPO,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
        )
        if ensure.returncode != 0:
            return f"fallback_gap_log={fallback}"
        summary = json.loads(ensure.stdout)
        step = summary.get("next_step") or {}
        step_id = step.get("step_id")
        session_id = summary.get("session_id")
        if session_id and step_id:
            subprocess.run(
                [
                    sys.executable,
                    str(kernel_script),
                    "--root",
                    str(kernel_root),
                    "analyze-gap",
                    "--session-id",
                    session_id,
                    "--step-id",
                    step_id,
                    "--observation",
                    f"intent tool router unsupported: {reason}",
                ],
                cwd=REPO,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=30,
            )
            return f"kernel_session={session_id} fallback_gap_log={fallback}"
    except Exception:
        return f"fallback_gap_log={fallback}"
    return f"fallback_gap_log={fallback}"


def is_executor_capability_gap(output: str) -> bool:
    lowered = output.lower()
    return (
        "capability_gap" in lowered
        or "没有已验证" in output
        or "缺少已验证" in output
        or "missing verified" in lowered
        or "missing executor" in lowered
    )


def handle(
    text: str,
    channel: str,
    user_id: str,
    message_timestamp: str,
    *,
    registry_path: Path = DEFAULT_REGISTRY,
    kernel_root: Path = DEFAULT_KERNEL_ROOT,
    replay_depth: int = 0,
    registry_override: dict[str, Any] | None = None,
    context: str = "",
) -> RouterResult:
    registry = registry_override or load_registry(registry_path)
    timeout_seconds = int(registry.get("defaults", {}).get("timeout_seconds") or 1800)
    result = handle_event(
        text=text,
        channel=channel,
        user_id=user_id,
        message_timestamp=message_timestamp,
        registry=registry,
        context=context,
        kernel_root=kernel_root,
        timeout_seconds=timeout_seconds,
        extract_args=extract_args,
        run_tool=run_tool,
        format_reply=format_reply,
        audit_intent=audit_intent,
        evaluate_result=evaluate_result,
    )
    binding = result.binding
    tool = binding.tool if binding else None
    frame = result.intent_frame
    classification = Classification(
        str(tool.get("intent_id")) if tool else None,
        str(tool.get("tool_id")) if tool else None,
        float(frame.confidence) if frame else 0.0,
        str(frame.reason) if frame else result.route_kind,
        tool,
        asdict(frame) if frame else None,
    )
    return RouterResult(result.status, result.reply, classification, result.args, result.returncode, result.route_kind)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--channel", default="discord_dm")
    parser.add_argument("--user-id", default="unknown")
    parser.add_argument("--message-timestamp", default=utc_now())
    parser.add_argument("--context", default="")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--kernel-root", type=Path, default=Path(os.environ.get("OPENCLAW_AGENT_KERNEL_ROOT", DEFAULT_KERNEL_ROOT)))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--classify-only", action="store_true")
    parser.add_argument("--intent-frame-only", action="store_true")
    args = parser.parse_args()
    if args.classify_only or args.intent_frame_only:
        registry = load_registry(args.registry)
        frame = infer_intent_frame(args.text, context=args.context, registry=registry)
        binding = bind_tool(frame, registry)
        review = review_intent_frame(frame, binding.tool, args.text) if binding.tool else None
        payload = {
            "intent_frame": asdict(frame),
            "binding": asdict(binding),
            "semantic_review": asdict(review) if review else None,
            "would_execute": bool(binding.tool and (review is None or review.passed)),
            "route_kind": binding.status,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    result = handle(
        args.text,
        args.channel,
        args.user_id,
        args.message_timestamp,
        registry_path=args.registry,
        kernel_root=args.kernel_root,
        context=args.context,
    )
    if args.json:
        payload = asdict(result)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(result.reply)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
