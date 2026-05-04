#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = REPO / "config" / "openclaw" / "intent_tools.json"
DEFAULT_KERNEL_ROOT = Path("/var/lib/openclaw/.openclaw/workspace/agent_society_kernel")

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
    r"(请|帮|麻烦|需要|处理|执行|完成|安排|调查|排查|修复|检查|查询|查看|触发|重跑|补跑|取消|修改|调整|设置|部署|重启|创建|生成|汇报|报告|发到|转发)",
    re.IGNORECASE,
)


def classify_unregistered_intent(text: str) -> str:
    normalized_prompt = re.sub(r"\s+", " ", text or "").strip()
    if not normalized_prompt:
        return "chat"
    if CHAT_ONLY_PATTERN.fullmatch(normalized_prompt):
        return "chat"
    # Short messages without an action verb are still chat, not capability gaps.
    if len(normalize_text(normalized_prompt)) <= 12 and not TASK_VERB_PATTERN.search(normalized_prompt):
        return "chat"
    if TASK_VERB_PATTERN.search(normalized_prompt):
        return "unsupported_task"
    return "chat"


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
    proc = subprocess.run(
        cmd,
        cwd=REPO,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout_seconds,
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


def handle(
    text: str,
    channel: str,
    user_id: str,
    message_timestamp: str,
    *,
    registry_path: Path = DEFAULT_REGISTRY,
    kernel_root: Path = DEFAULT_KERNEL_ROOT,
) -> RouterResult:
    registry = load_registry(registry_path)
    classification = classify(text, channel, user_id, registry)
    if classification.tool is None:
        route_kind = classify_unregistered_intent(text)
        if route_kind == "chat":
            return RouterResult("chat", "", classification, {}, 0, route_kind="chat")
        gap_ref = record_capability_gap(text, channel, user_id, classification.reason, kernel_root)
        reply = "\n".join(
            [
                "汤猴已收到私信，但没有找到已注册的确定性工具。",
                "状态：未执行，已记录能力缺口。",
                f"原因：{classification.reason}",
                f"记录：{gap_ref}",
            ]
        )
        return RouterResult("unsupported", reply, classification, {}, 0, route_kind="unsupported_task")

    try:
        args = extract_args(classification.tool, text, message_timestamp)
        timeout_seconds = int(registry.get("defaults", {}).get("timeout_seconds") or 1800)
        returncode, output = run_tool(classification.tool, args, timeout_seconds)
        reply = format_reply(classification.tool, args, returncode, output)
        if returncode != 0 and classification.tool.get("failure_policy") == "reply_failure_and_record_gap":
            record_capability_gap(text, channel, user_id, output or f"tool failed: {classification.tool_id}", kernel_root)
        return RouterResult("ok" if returncode == 0 else "failed", reply, classification, args, returncode, route_kind="registered_task")
    except Exception as exc:
        reason = str(exc)
        gap_ref = record_capability_gap(text, channel, user_id, reason, kernel_root)
        reply = "\n".join(
            [
                "汤猴事件入口未能执行该工具。",
                f"工具：{classification.tool_id}",
                f"原因：{reason}",
                f"记录：{gap_ref}",
            ]
        )
        return RouterResult("failed", reply, classification, {}, 1, route_kind="registered_task")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--channel", default="discord_dm")
    parser.add_argument("--user-id", default="unknown")
    parser.add_argument("--message-timestamp", default=utc_now())
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--kernel-root", type=Path, default=Path(os.environ.get("OPENCLAW_AGENT_KERNEL_ROOT", DEFAULT_KERNEL_ROOT)))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--classify-only", action="store_true")
    args = parser.parse_args()
    if args.classify_only:
        registry = load_registry(args.registry)
        classification = classify(args.text, args.channel, args.user_id, registry)
        extracted = {}
        if classification.tool:
            extracted = extract_args(classification.tool, args.text, args.message_timestamp)
        payload = {
            "classification": asdict(classification),
            "args": extracted,
            "would_execute": bool(classification.tool),
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
    )
    if args.json:
        payload = asdict(result)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(result.reply)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
