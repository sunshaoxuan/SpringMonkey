#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from harness_intent_agent import IntentFrame
from nl_time_range import requested_range_spec


@dataclass
class SemanticReview:
    passed: bool
    reason: str
    conflict_type: str = ""


WEB_RESEARCH_UNSAFE_RE = re.compile(
    r"(登录|登入|log\s?in|sign\s?in|购买|付款|支付|取消|修改|改配置|设置|提交|删除|密码|token|secret|密钥|账号|account)",
    re.IGNORECASE,
)


def review_intent_frame(frame: IntentFrame, tool: dict[str, Any] | None, original_text: str) -> SemanticReview:
    if frame.conversation_mode == "task" and not tool:
        return SemanticReview(False, "task frame has no bound tool", "tool_binding_missing")
    if tool:
        write_tool = bool(tool.get("write_operation"))
        if write_tool and frame.safety == "readonly":
            return SemanticReview(False, "model selected write tool but marked safety readonly", "safety_mismatch")
        if not write_tool and frame.safety in {"write", "destructive", "credential"}:
            return SemanticReview(False, "model selected readonly tool for unsafe frame", "safety_mismatch")
    if frame.domain == "timescar" and frame.action == "query":
        params = frame.parameters or {}
        text_spec = requested_range_spec(frame.canonical_text or original_text)
        if text_spec and params:
            duration = params.get("duration_hours")
            offset = params.get("offset_hours", 0)
            try:
                duration_i = int(duration)
                offset_i = int(offset)
            except (TypeError, ValueError):
                return SemanticReview(False, "timescar query frame has non-numeric time parameters", "parameter_invalid")
            if duration_i != text_spec.duration_hours or offset_i != text_spec.offset_hours:
                return SemanticReview(
                    False,
                    f"model time parameters conflict with verifier: model duration={duration_i} offset={offset_i}; verifier duration={text_spec.duration_hours} offset={text_spec.offset_hours}",
                    "semantic_verifier_conflict",
                )
    if frame.domain == "web" and frame.action == "research":
        if frame.safety != "readonly":
            return SemanticReview(False, "web research must be readonly", "safety_mismatch")
        combined = f"{original_text}\n{frame.canonical_text}"
        if WEB_RESEARCH_UNSAFE_RE.search(combined):
            return SemanticReview(False, "web research cannot handle write, credential, booking, or account operations", "unsafe_web_research")
    return SemanticReview(True, "semantic frame accepted")
