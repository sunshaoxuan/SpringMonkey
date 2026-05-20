#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable

from model_fallback_client import chat_with_fallback

CHAT_KIND = "chat"
TASK_KIND = "task"

ATOMIC_DEPTH = "atomic"
STAGED_DEPTH = "staged"
AGENTIC_DEPTH = "agentic"

SIMPLE_CHAT_PATTERN = re.compile(
    r"^\s*(你好|您好|hi|hello|早上好|晚上好|谢谢|thanks|ok|好的|收到|嗯|在吗|拜拜|bye)[!！,.，。 ]*\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EntryPolicyFrame:
    interaction_kind: str
    execution_depth: str
    apply_agent_society: bool
    apply_operational_execution: bool
    apply_self_improvement: bool
    reasoning_summary: str = ""


def normalize_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt or "").strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"model did not return JSON: {raw[:200]}")
    data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("model returned non-object JSON")
    return data


def _validate_frame(data: dict[str, Any]) -> EntryPolicyFrame:
    interaction_kind = str(data.get("interaction_kind") or CHAT_KIND)
    execution_depth = str(data.get("execution_depth") or ATOMIC_DEPTH)
    if interaction_kind not in {CHAT_KIND, TASK_KIND}:
        raise ValueError(f"invalid interaction_kind: {interaction_kind}")
    if execution_depth not in {ATOMIC_DEPTH, STAGED_DEPTH, AGENTIC_DEPTH}:
        raise ValueError(f"invalid execution_depth: {execution_depth}")
    return EntryPolicyFrame(
        interaction_kind=interaction_kind,
        execution_depth=execution_depth,
        apply_agent_society=bool(data.get("apply_agent_society")),
        apply_operational_execution=bool(data.get("apply_operational_execution")),
        apply_self_improvement=bool(data.get("apply_self_improvement")),
        reasoning_summary=str(data.get("reasoning_summary") or ""),
    )


def _simple_frame(prompt: str, *, is_direct: bool, is_heartbeat: bool) -> EntryPolicyFrame | None:
    text = normalize_prompt(prompt)
    if is_heartbeat or not is_direct or not text:
        return EntryPolicyFrame(CHAT_KIND, ATOMIC_DEPTH, False, False, False, "non-direct, heartbeat, or empty")
    if SIMPLE_CHAT_PATTERN.fullmatch(text):
        return EntryPolicyFrame(CHAT_KIND, ATOMIC_DEPTH, False, False, False, "simple liveness or acknowledgement")
    return None


def build_entry_policy_prompt(prompt: str, *, is_direct: bool, is_heartbeat: bool) -> list[dict[str, str]]:
    system = (
        "You are OpenClaw's entry-policy classifier. Return strict JSON only. "
        "Schema: {interaction_kind, execution_depth, apply_agent_society, apply_operational_execution, apply_self_improvement, reasoning_summary}. "
        "interaction_kind: chat|task. execution_depth: atomic|staged|agentic. "
        "This is a semantic classifier. Do not use keyword matching, regex matching, token hits, or example phrase matching to decide intent. "
        "Use meaning, user goal, implied workflow, side effects, required observations, and repair needs. "
        "Use chat only for casual conversation, liveness, acknowledgements, or explanations that require no durable task state. "
        "Use task when the user asks for work to be done, state to be inspected or changed, facts to be researched, a process to be monitored, a result to be delivered, or a previous failure to be repaired. "
        "Use atomic only for a single-step task with no meaningful hidden state or follow-up. "
        "Use staged when the request naturally requires multiple observations, tools, verification, delivery, or a final report. "
        "Use agentic when the request requires dynamic replanning, self-repair, tool creation/refinement, debugging, deployment validation, or ongoing improvement. "
        "apply_operational_execution means the task needs real tool/browser/system execution, not just a conversational answer. "
        "apply_self_improvement means the task is about repairing or improving OpenClaw/Tanghou's own capabilities, regressions, tools, routing, tests, deployment, or reliability. "
        "If uncertain between chat and task, choose task with atomic depth only if the user is asking for work; otherwise choose chat. "
    )
    user = "\n".join(
        [
            f"is_direct={str(is_direct).lower()}",
            f"is_heartbeat={str(is_heartbeat).lower()}",
            "Current message:",
            prompt,
        ]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def classify_entry_policy(
    prompt: str,
    *,
    is_direct: bool = True,
    is_heartbeat: bool = False,
    model_caller: Callable[[list[dict[str, str]]], str] | None = None,
) -> EntryPolicyFrame:
    simple = _simple_frame(prompt, is_direct=is_direct, is_heartbeat=is_heartbeat)
    if simple is not None:
        return simple
    override = os.environ.get("OPENCLAW_ENTRY_POLICY_FRAME_JSON", "").strip()
    if override:
        return _validate_frame(_extract_json_object(override))
    messages = build_entry_policy_prompt(prompt, is_direct=is_direct, is_heartbeat=is_heartbeat)
    try:
        content = model_caller(messages) if model_caller else chat_with_fallback(messages, timeout=25, temperature=0)[0]
        return _validate_frame(_extract_json_object(content))
    except Exception as exc:
        # Conservative fallback is not a semantic router: it avoids keyword
        # branching and does not inject task protocols when the semantic
        # classifier is unavailable.
        return EntryPolicyFrame(CHAT_KIND, ATOMIC_DEPTH, False, False, False, f"entry policy model unavailable: {type(exc).__name__}: {exc}")


def classify_interaction_kind(prompt: str, *, is_direct: bool = True, is_heartbeat: bool = False) -> str:
    return classify_entry_policy(prompt, is_direct=is_direct, is_heartbeat=is_heartbeat).interaction_kind


def classify_execution_depth(prompt: str) -> str:
    return classify_entry_policy(prompt).execution_depth


def build_multistep_task_protocol(prompt: str, *, execution_depth: str | None = None) -> str:
    depth = execution_depth or classify_execution_depth(prompt)
    if depth == ATOMIC_DEPTH:
        return ""
    depth_label = "staged" if depth == STAGED_DEPTH else "agentic"
    lines = [
        "[runtime-task-creation-policy]",
        f"execution_depth: {depth_label}",
        "This is a real task, not casual chat.",
        "Intent understanding, task decomposition, and tool choice must be made through the LLM semantic contract layer, not keyword/regex routing.",
        "Keywords or regex may only be used after a tool is selected for deterministic low-level parsing such as timestamps, IDs, URLs, or HTML fields.",
        "You must decide goal, tasks, steps, tools, observations, and success checks before claiming completion.",
        "If the task involves websites, login, querying, searching, submission, translation, summarization, reporting, or delivery, treat it as multi-step by default.",
        "Write or refine helper tools when repeated capability gaps appear, validate them, and reuse them.",
        "Keep visible progress updates and a final result or blocker report.",
    ]
    if depth == AGENTIC_DEPTH:
        lines.extend(
            [
                "This task is agentic. You must dynamically replan after observations instead of following a fixed one-shot script.",
                "If a new reusable tool is needed, create it, debug it, validate it, and fold it back into the task.",
            ]
        )
    else:
        lines.append("This task is staged. Expose the phases and failure surfaces instead of hiding them in one black-box exec.")
    return "\n".join(lines)


def should_apply_operational_execution_protocol(prompt: str, *, is_direct: bool = True, is_heartbeat: bool = False) -> bool:
    return classify_entry_policy(prompt, is_direct=is_direct, is_heartbeat=is_heartbeat).apply_operational_execution


def should_apply_agent_society_protocol(prompt: str, *, is_direct: bool = True, is_heartbeat: bool = False) -> bool:
    return classify_entry_policy(prompt, is_direct=is_direct, is_heartbeat=is_heartbeat).apply_agent_society


def should_apply_self_improvement_protocol(prompt: str, *, is_direct: bool = True, is_heartbeat: bool = False) -> bool:
    return classify_entry_policy(prompt, is_direct=is_direct, is_heartbeat=is_heartbeat).apply_self_improvement


__all__ = [
    "AGENTIC_DEPTH",
    "ATOMIC_DEPTH",
    "CHAT_KIND",
    "TASK_KIND",
    "STAGED_DEPTH",
    "EntryPolicyFrame",
    "build_entry_policy_prompt",
    "build_multistep_task_protocol",
    "classify_entry_policy",
    "classify_execution_depth",
    "classify_interaction_kind",
    "normalize_prompt",
    "should_apply_agent_society_protocol",
    "should_apply_operational_execution_protocol",
    "should_apply_self_improvement_protocol",
]
