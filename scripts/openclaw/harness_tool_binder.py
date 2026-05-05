#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harness_intent_agent import IntentFrame


@dataclass
class ToolBinding:
    status: str
    tool: dict[str, Any] | None
    reason: str
    confidence: float = 0.0


def _tool_by_id(registry: dict[str, Any], tool_id: str) -> dict[str, Any] | None:
    return next((item for item in registry.get("tools", []) if str(item.get("tool_id")) == tool_id), None)


def bind_tool(frame: IntentFrame, registry: dict[str, Any]) -> ToolBinding:
    if frame.conversation_mode == "chat":
        return ToolBinding("chat", None, "chat frame does not require a tool", frame.confidence)
    if frame.conversation_mode in {"clarification", "gap"}:
        return ToolBinding(frame.conversation_mode, None, frame.reason, frame.confidence)
    for candidate in frame.tool_candidates:
        tool_id = str(candidate.get("tool_id") or "")
        if not tool_id:
            continue
        tool = _tool_by_id(registry, tool_id)
        if tool:
            return ToolBinding("bound", tool, str(candidate.get("reason") or frame.reason), float(candidate.get("confidence") or frame.confidence))
    for tool in registry.get("tools", []):
        domain_ok = str(tool.get("domain") or "") == frame.domain
        actions = [str(item) for item in tool.get("actions", [])]
        action_ok = frame.action in actions
        if domain_ok and action_ok:
            return ToolBinding("bound", tool, f"bound by capability domain/action from IntentFrame: {frame.domain}/{frame.action}", frame.confidence)
    return ToolBinding("gap", None, f"no registered tool for IntentFrame domain/action: {frame.domain}/{frame.action}", frame.confidence)
