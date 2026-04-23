#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


UTC = timezone.utc


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def split_candidate_clauses(prompt: str) -> list[str]:
    parts = re.split(r"[;\n]+|(?:，|。|；)|(?:\bthen\b)|(?:\band\b)", prompt, flags=re.IGNORECASE)
    clauses = [normalize_text(part) for part in parts]
    return [clause for clause in clauses if clause]


def infer_goal(prompt: str) -> str:
    text = normalize_text(prompt)
    if not text:
        return "advance the user request"
    return text[:240]


def infer_intent_kind(text: str) -> str:
    lowered = text.lower()
    if re.search(r"登录|登入|log\s?in|sign\s?in|打开|访问|进入|click|点击|search|查找|visit|open", text, re.IGNORECASE):
        return "operational"
    if re.search(r"验证|verify|确认|check|检查", text, re.IGNORECASE):
        return "verification"
    if re.search(r"汇报|报告|report|status|总结|summary", text, re.IGNORECASE):
        return "reporting"
    if re.search(r"记录|记住|memory|save|保存", lowered, re.IGNORECASE):
        return "memory"
    return "general"


@dataclass
class Goal:
    goal_id: str
    primary: str
    secondary: list[str]
    completion_criteria: list[str]
    boundaries: list[str]
    status: str = "active"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class Intent:
    intent_id: str
    parent_goal_id: str
    source: str
    kind: str
    priority: int
    status: str
    reason_to_exist: str
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class Task:
    task_id: str
    parent_intent_id: str
    owner: str
    summary: str
    success_condition: str
    evidence_required: str
    status: str
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class Step:
    step_id: str
    parent_task_id: str
    summary: str
    tool_candidates: list[str]
    chosen_tool: str
    expected_observation: str
    actual_observation: str | None
    next_decision: str
    status: str
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class CapabilityGap:
    gap_id: str
    parent_step_id: str
    category: str
    summary: str
    severity: str
    proposed_repair: str
    proposed_tool_name: str | None
    status: str
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class FailurePattern:
    pattern_id: str
    signature: str
    category: str
    summary: str
    occurrence_count: int
    example_gap_ids: list[str]
    proposed_response: str
    proposed_helper_name: str | None
    status: str
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class HelperTool:
    tool_id: str
    name: str
    scope: str
    kind: str
    entrypoint: str
    status: str
    derived_from_gap_id: str | None
    notes: str
    validation_observation: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class PromotedHelperRecord:
    record_id: str
    name: str
    scope: str
    kind: str
    entrypoint: str
    source_tool_id: str
    source_gap_category: str | None
    validation_observation: str | None
    usage_count: int
    last_selected_at: str | None
    status: str
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class KernelSession:
    session_id: str
    created_at: str
    updated_at: str
    channel: str
    user_id: str
    raw_request: str
    goal: Goal
    intents: list[Intent]
    tasks: list[Task]
    steps: list[Step]
    observations: list[dict[str, Any]]
    capability_gaps: list[CapabilityGap]
    failure_patterns: list[FailurePattern]
    helper_tools: list[HelperTool]


class AgentSocietyKernel:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.sessions_dir = root / "sessions"
        self.registry_path = root / "helper_registry.json"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.ensure_workspace_bridge()

    def ensure_workspace_bridge(self) -> None:
        workspace = self.root.parent
        workspace.mkdir(parents=True, exist_ok=True)
        policy_file = workspace / "AGENT_SOCIETY_KERNEL.md"
        policy_text = """# Agent Society Kernel

This host has a minimal durable kernel for goal -> intent -> task -> step execution state.

State root:

- `/var/lib/openclaw/.openclaw/workspace/agent_society_kernel`

Current expectations:

- direct work may be represented as one goal with multiple intents
- intents may map to multiple tasks
- tasks map to concrete observable steps
- each step should identify current tool candidates and one chosen tool
- observations should be written back into durable state instead of living only in prompt text
- repeated failures should be classified into durable capability gaps
- stable repeated gaps should produce helper tool proposals instead of blind retries

Current limitation:

- this kernel is a state and execution-loop foundation
- it is not yet a full native OpenClaw scheduler
"""
        policy_file.write_text(policy_text, encoding="utf-8")

    def bootstrap_session(self, prompt: str, channel: str, user_id: str) -> KernelSession:
        session_id = make_id("session")
        goal_id = make_id("goal")
        clauses = split_candidate_clauses(prompt) or [normalize_text(prompt) or "advance the user request"]
        goal = Goal(
            goal_id=goal_id,
            primary=infer_goal(prompt),
            secondary=[],
            completion_criteria=["produce a verified result or a concrete blocker", "keep work converged to the primary goal"],
            boundaries=["avoid unbounded branching", "prefer tool-grounded execution over unsupported claims"],
        )
        intents: list[Intent] = []
        tasks: list[Task] = []
        steps: list[Step] = []
        for index, clause in enumerate(clauses, start=1):
            intent_id = make_id("intent")
            task_id = make_id("task")
            step_id = make_id("step")
            intent_kind = infer_intent_kind(clause)
            intents.append(
                Intent(
                    intent_id=intent_id,
                    parent_goal_id=goal.goal_id,
                    source="user_request",
                    kind=intent_kind,
                    priority=index,
                    status="pending",
                    reason_to_exist=clause,
                )
            )
            tasks.append(
                Task(
                    task_id=task_id,
                    parent_intent_id=intent_id,
                    owner="decomposer",
                    summary=clause,
                    success_condition=f"the request segment is completed or explicitly blocked: {clause}",
                    evidence_required="observed tool output, machine state, or an explicit blocker",
                    status="pending",
                )
            )
            steps.append(
                Step(
                    step_id=step_id,
                    parent_task_id=task_id,
                    summary=clause,
                    tool_candidates=self._default_tools_for_intent(intent_kind),
                    chosen_tool=self._default_tools_for_intent(intent_kind)[0],
                    expected_observation="a concrete observation that advances or blocks the task",
                    actual_observation=None,
                    next_decision="choose the next best bounded step based on observation",
                    status="pending",
                )
            )
        session = KernelSession(
            session_id=session_id,
            created_at=utc_now(),
            updated_at=utc_now(),
            channel=channel,
            user_id=user_id,
            raw_request=prompt,
            goal=goal,
            intents=intents,
            tasks=tasks,
            steps=steps,
            observations=[],
            capability_gaps=[],
            failure_patterns=[],
            helper_tools=[],
        )
        self.save_session(session)
        return session

    def _default_tools_for_intent(self, intent_kind: str) -> list[str]:
        if intent_kind == "operational":
            return ["browser", "web_search", "shell"]
        if intent_kind == "verification":
            return ["shell", "browser", "web_fetch"]
        if intent_kind == "reporting":
            return ["message"]
        if intent_kind == "memory":
            return ["shell", "memory"]
        return ["shell", "browser"]

    def save_session(self, session: KernelSession) -> Path:
        session.updated_at = utc_now()
        session.goal.updated_at = session.updated_at
        path = self.sessions_dir / f"{session.session_id}.json"
        path.write_text(json.dumps(asdict(session), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def load_session(self, session_id: str) -> KernelSession:
        path = self.sessions_dir / f"{session_id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return KernelSession(
            session_id=data["session_id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            channel=data["channel"],
            user_id=data["user_id"],
            raw_request=data["raw_request"],
            goal=Goal(**data["goal"]),
            intents=[Intent(**item) for item in data["intents"]],
            tasks=[Task(**item) for item in data["tasks"]],
            steps=[Step(**item) for item in data["steps"]],
            observations=data.get("observations", []),
            capability_gaps=[CapabilityGap(**item) for item in data.get("capability_gaps", [])],
            failure_patterns=[FailurePattern(**item) for item in data.get("failure_patterns", [])],
            helper_tools=[HelperTool(**item) for item in data.get("helper_tools", [])],
        )

    def next_step(self, session: KernelSession) -> Step | None:
        pending_steps = [step for step in session.steps if step.status in {"pending", "in_progress"}]
        if not pending_steps:
            return None
        registry_helpers = self._select_registry_helpers_for_session(session)
        validated_helpers = [
            tool for tool in session.helper_tools
            if tool.status in {"validated", "promoted"} and tool.entrypoint
        ]
        helper_candidates = registry_helpers + [tool.entrypoint for tool in validated_helpers if tool.entrypoint not in registry_helpers]
        for step in pending_steps:
            if helper_candidates:
                merged = helper_candidates + [candidate for candidate in step.tool_candidates if candidate not in helper_candidates]
                step.tool_candidates = merged
                if registry_helpers:
                    step.chosen_tool = registry_helpers[0]
                elif step.chosen_tool not in merged:
                    step.chosen_tool = merged[0]
            self._apply_learned_patterns_to_step(session, step)
        task_order = {task.task_id: index for index, task in enumerate(session.tasks)}
        pending_steps.sort(key=lambda step: task_order.get(step.parent_task_id, 10**6))
        return pending_steps[0]

    def _select_registry_helpers_for_session(self, session: KernelSession) -> list[str]:
        registry = self.load_promoted_helper_registry()
        if not registry:
            return []
        relevant = self._infer_relevant_helper_scopes(session)
        chosen: list[str] = []
        updated = False
        for record in registry:
            if record.status != "promoted":
                continue
            if relevant and record.scope not in relevant and record.source_gap_category not in relevant:
                continue
            if record.entrypoint not in chosen:
                chosen.append(record.entrypoint)
                record.usage_count += 1
                record.last_selected_at = utc_now()
                record.updated_at = utc_now()
                updated = True
        if updated:
            self.save_promoted_helper_registry(registry)
        return chosen

    def _infer_relevant_helper_scopes(self, session: KernelSession) -> set[str]:
        text = " ".join(
            [session.raw_request, session.goal.primary] + [step.summary for step in session.steps]
        ).lower()
        scopes: set[str] = set()
        if any(token in text for token in ("timeout", "timed out", "etimedout", "stalled", "hang", "hung", "卡住")):
            scopes.add("runtime_timeout")
        if any(token in text for token in ("missing tool", "missing helper", "unsupported", "not found", "缺少工具")):
            scopes.add("tool_missing")
        if any(token in text for token in ("bundle", "patch", "drift", "anchor", "selector", "upgrade")):
            scopes.add("runtime_drift")
        if any(token in text for token in ("no response", "blocked", "stuck", "无响应", "阻塞")):
            scopes.add("execution_blocked")
        if any(token in text for token in ("discover", "unknown system", "入口未知", "unclear target")):
            scopes.add("target_discovery_missing")
        return scopes

    def record_observation(self, session: KernelSession, step_id: str, observation: str, next_decision: str, status: str) -> Step:
        for step in session.steps:
            if step.step_id != step_id:
                continue
            step.actual_observation = normalize_text(observation)
            step.next_decision = normalize_text(next_decision)
            step.status = status
            step.updated_at = utc_now()
            session.observations.append(
                {
                    "step_id": step_id,
                    "observation": step.actual_observation,
                    "next_decision": step.next_decision,
                    "status": status,
                    "recorded_at": utc_now(),
                }
            )
            self._sync_task_and_intent_status(session, step)
            self.save_session(session)
            return step
        raise KeyError(f"step not found: {step_id}")

    def analyze_capability_gap(self, session: KernelSession, step_id: str, observation: str) -> CapabilityGap:
        step = next((item for item in session.steps if item.step_id == step_id), None)
        if step is None:
            raise KeyError(f"step not found: {step_id}")
        normalized = normalize_text(observation)
        lowered = normalized.lower()
        category = "execution_blocked"
        severity = "medium"
        proposed_repair = "narrow the blocker and choose the next bounded recovery step"
        proposed_tool_name: str | None = None

        if any(token in lowered for token in ("timeout", "timed out", "卡住", "hang", "hung", "stalled", "etimedout", "first token", "visible progress")):
            category = "runtime_timeout"
            severity = "high"
            proposed_repair = "retry with a bounded timeout-recovery path and inspect runtime/tool latency before continuing"
        elif any(token in lowered for token in ("not found", "找不到", "missing tool", "no tool", "unsupported")):
            category = "tool_missing"
            severity = "high"
            proposed_tool_name = self._suggest_helper_tool_name(step)
            proposed_repair = f"create or refine helper tool `{proposed_tool_name}` for this repeated gap"
        elif any(token in lowered for token in ("selector", "anchor", "bundle", "patch", "drift", "版本", "锚点")):
            category = "runtime_drift"
            severity = "high"
            proposed_tool_name = "runtime_bundle_probe"
            proposed_repair = "probe the active runtime artifact, verify markers, and patch the currently active bundle instead of guessing by filename"
        elif any(token in lowered for token in ("login", "2fa", "验证码", "permission", "forbidden", "denied", "权限")):
            category = "access_blocked"
            severity = "high"
            proposed_repair = "classify the access blocker, preserve current state, and request or discover the minimum missing credential or approval"
        elif any(token in lowered for token in ("unknown system", "不确定系统", "unclear target", "入口未知")):
            category = "target_discovery_missing"
            severity = "medium"
            proposed_tool_name = self._suggest_helper_tool_name(step, suffix="discovery")
            proposed_repair = f"create a bounded discovery helper such as `{proposed_tool_name}` to identify the real target before continuing"

        gap = CapabilityGap(
            gap_id=make_id("gap"),
            parent_step_id=step_id,
            category=category,
            summary=normalized[:400] or "unclassified execution gap",
            severity=severity,
            proposed_repair=proposed_repair,
            proposed_tool_name=proposed_tool_name,
            status="open",
        )
        session.capability_gaps.append(gap)
        pattern = self._record_failure_pattern(session, step, gap)
        self._apply_learned_pattern_to_gap(gap, pattern, step)
        self.save_session(session)
        return gap

    def _record_failure_pattern(self, session: KernelSession, step: Step, gap: CapabilityGap) -> FailurePattern:
        signature = self._infer_failure_pattern_signature(step, gap)
        summary = self._infer_failure_pattern_summary(gap)
        pattern = next((item for item in session.failure_patterns if item.signature == signature), None)
        if pattern is None:
            pattern = FailurePattern(
                pattern_id=make_id("pattern"),
                signature=signature,
                category=gap.category,
                summary=summary,
                occurrence_count=1,
                example_gap_ids=[gap.gap_id],
                proposed_response=gap.proposed_repair,
                proposed_helper_name=gap.proposed_tool_name,
                status="candidate",
            )
            session.failure_patterns.append(pattern)
            return pattern
        pattern.occurrence_count += 1
        if gap.gap_id not in pattern.example_gap_ids:
            pattern.example_gap_ids = (pattern.example_gap_ids + [gap.gap_id])[-5:]
        pattern.summary = summary
        pattern.proposed_response = gap.proposed_repair
        if gap.proposed_tool_name:
            pattern.proposed_helper_name = gap.proposed_tool_name
        pattern.status = self._infer_failure_pattern_status(pattern)
        pattern.updated_at = utc_now()
        return pattern

    def _apply_learned_pattern_to_gap(self, gap: CapabilityGap, pattern: FailurePattern, step: Step) -> None:
        if pattern.status != "learned":
            return
        gap.proposed_repair = pattern.proposed_response
        if pattern.proposed_helper_name:
            gap.proposed_tool_name = pattern.proposed_helper_name
        elif not gap.proposed_tool_name:
            gap.proposed_tool_name = self._suggest_helper_tool_name(step, suffix="repair")
        gap.updated_at = utc_now()

    def _apply_learned_patterns_to_step(self, session: KernelSession, step: Step) -> None:
        learned_patterns = [item for item in session.failure_patterns if item.status == "learned"]
        if not learned_patterns:
            return
        related_gaps = [gap for gap in session.capability_gaps if gap.parent_step_id == step.step_id]
        related_categories = {gap.category for gap in related_gaps}
        applicable: list[FailurePattern] = []
        if related_categories:
            applicable.extend([item for item in learned_patterns if item.category in related_categories])
        else:
            step_text = f"{step.summary} {step.expected_observation} {step.next_decision}".lower()
            for item in learned_patterns:
                tokens = [token for token in item.signature.split(":", 1)[-1].split("_") if token and token != "generic"]
                if tokens and any(token in step_text for token in tokens):
                    applicable.append(item)
            if not applicable:
                applicable.extend(learned_patterns)
        if not applicable:
            return
        helper_by_name = {
            tool.name: tool.entrypoint
            for tool in session.helper_tools
            if tool.status in {"validated", "promoted"} and tool.entrypoint
        }
        for pattern in applicable:
            if pattern.proposed_helper_name:
                entrypoint = helper_by_name.get(pattern.proposed_helper_name)
                if entrypoint:
                    if entrypoint not in step.tool_candidates:
                        step.tool_candidates = [entrypoint] + step.tool_candidates
                    deduped_candidates: list[str] = []
                    for candidate in step.tool_candidates:
                        if candidate not in deduped_candidates:
                            deduped_candidates.append(candidate)
                    step.tool_candidates = deduped_candidates
                    step.chosen_tool = entrypoint
            if pattern.proposed_response:
                learned_note = f"prefer learned repair path: {pattern.proposed_response}"
                if learned_note not in step.next_decision:
                    step.next_decision = normalize_text(f"{learned_note}; {step.next_decision}")
            if step.expected_observation and "learned pattern" not in step.expected_observation.lower():
                step.expected_observation = normalize_text(f"{step.expected_observation}; verify with learned pattern guidance")
            step.updated_at = utc_now()

    def _infer_failure_pattern_signature(self, step: Step, gap: CapabilityGap) -> str:
        semantic = self._semantic_tokens_for_gap(gap, step)
        deduped: list[str] = []
        for token in semantic:
            if token not in deduped:
                deduped.append(token)
        semantic_shape = "_".join(deduped[:6]).strip("_") or "generic"
        return f"{gap.category}:{semantic_shape}"

    def _semantic_tokens_for_gap(self, gap: CapabilityGap, step: Step) -> list[str]:
        text = f"{gap.summary} {step.summary}".lower()
        raw_tokens = re.findall(r"[a-z0-9]+", text)
        stopwords = {"the", "and", "for", "with", "while", "again", "before", "after", "out", "this", "that", "from"}
        synonyms = {
            "timed": "timeout",
            "stalled": "timeout",
            "stall": "timeout",
            "hang": "timeout",
            "hung": "timeout",
            "latency": "waiting",
            "first": "first",
            "packet": "response",
            "token": "response",
            "generated": "response",
            "empty": "response",
            "selector": "selector",
            "anchor": "anchor",
            "bundle": "bundle",
            "patch": "patch",
            "renamed": "drift",
            "rename": "drift",
            "version": "drift",
            "missing": "missing",
            "unsupported": "missing",
            "absent": "missing",
            "helper": "tool",
            "script": "tool",
        }
        tokens = [synonyms.get(token, token) for token in raw_tokens if token not in stopwords]

        if gap.category == "runtime_timeout":
            bucket: list[str] = []
            if any(token in text for token in ("timeout", "timed out", "etimedout", "stalled", "hang", "hung", "卡住")):
                bucket.append("timeout")
            if any(token in text for token in ("first response", "first token", "first packet", "visible progress")):
                bucket.append("response")
                bucket.append("first")
            elif any(token in text for token in ("response", "output", "visible")):
                bucket.append("response")
            return bucket or ["timeout"]

        if gap.category == "runtime_drift":
            bucket = []
            if any(token in text for token in ("bundle", "dist", "artifact")):
                bucket.append("bundle")
            if any(token in text for token in ("anchor", "selector", "patch", "marker")):
                bucket.append("anchor")
            if any(token in text for token in ("drift", "renamed", "rename", "version", "upgrade", "update")):
                bucket.append("drift")
            return bucket or ["drift"]

        if gap.category == "tool_missing":
            bucket = []
            if any(token in text for token in ("missing", "not found", "no such", "unsupported", "absent")):
                bucket.append("missing")
            if any(token in text for token in ("tool", "helper", "script")):
                bucket.append("tool")
            if "watchdog" in text:
                bucket.append("watchdog")
            if "browser" in text:
                bucket.append("browser")
            return bucket or ["missing", "tool"]

        if gap.category == "execution_blocked":
            bucket = []
            if any(token in text for token in ("no response", "empty response", "no result", "silent output")):
                bucket.append("response")
            if any(token in text for token in ("blocked", "stuck", "cannot continue", "failed to continue")):
                bucket.append("blocked")
            if "direct" in text:
                bucket.append("direct")
            if "task" in text:
                bucket.append("task")
            return bucket or ["blocked"]

        return tokens or [gap.category]

    def _infer_failure_pattern_summary(self, gap: CapabilityGap) -> str:
        base = gap.summary[:160] if gap.summary else gap.category
        return f"{gap.category} recurring pattern around: {base}"[:240]

    def _infer_failure_pattern_status(self, pattern: FailurePattern) -> str:
        if pattern.occurrence_count >= 3:
            return "learned"
        if pattern.occurrence_count >= 2:
            return "emerging"
        return "candidate"

    def register_helper_tool(
        self,
        session: KernelSession,
        name: str,
        scope: str,
        kind: str,
        entrypoint: str,
        notes: str,
        derived_from_gap_id: str | None = None,
    ) -> HelperTool:
        tool = HelperTool(
            tool_id=make_id("tool"),
            name=normalize_text(name),
            scope=normalize_text(scope),
            kind=normalize_text(kind),
            entrypoint=normalize_text(entrypoint),
            status="registered",
            derived_from_gap_id=derived_from_gap_id,
            notes=normalize_text(notes),
        )
        session.helper_tools.append(tool)
        if derived_from_gap_id:
            for gap in session.capability_gaps:
                if gap.gap_id == derived_from_gap_id:
                    gap.status = "addressing"
                    gap.updated_at = utc_now()
                    break
        self.save_session(session)
        return tool

    def propose_helper_from_gap(
        self,
        session: KernelSession,
        gap_id: str,
        kind: str,
        entrypoint: str,
        scope: str | None = None,
        notes: str | None = None,
    ) -> HelperTool:
        gap = next((item for item in session.capability_gaps if item.gap_id == gap_id), None)
        if gap is None:
            raise KeyError(f"gap not found: {gap_id}")
        if not gap.proposed_tool_name:
            parent_step = next((item for item in session.steps if item.step_id == gap.parent_step_id), None)
            if parent_step is None:
                raise ValueError(f"gap does not include a proposed tool name and parent step is missing: {gap_id}")
            gap.proposed_tool_name = self._suggest_helper_tool_name(parent_step, suffix="repair")
            gap.updated_at = utc_now()
        inferred_scope = normalize_text(scope or gap.category)
        inferred_notes = normalize_text(notes or gap.proposed_repair)
        for pattern in session.failure_patterns:
            if gap.gap_id in pattern.example_gap_ids or pattern.category == gap.category:
                if pattern.signature.startswith(f"{gap.category}:"):
                    pattern.proposed_helper_name = gap.proposed_tool_name
                    pattern.proposed_response = inferred_notes
                    pattern.updated_at = utc_now()
        return self.register_helper_tool(
            session=session,
            name=gap.proposed_tool_name,
            scope=inferred_scope,
            kind=kind,
            entrypoint=entrypoint,
            notes=inferred_notes,
            derived_from_gap_id=gap_id,
        )

    def validate_helper_tool(self, session: KernelSession, tool_id: str, observation: str, status: str) -> HelperTool:
        tool = next((item for item in session.helper_tools if item.tool_id == tool_id), None)
        if tool is None:
            raise KeyError(f"helper tool not found: {tool_id}")
        tool.validation_observation = normalize_text(observation)
        tool.status = status
        tool.updated_at = utc_now()
        if tool.derived_from_gap_id:
            for gap in session.capability_gaps:
                if gap.gap_id != tool.derived_from_gap_id:
                    continue
                if status in {"validated", "promoted"}:
                    gap.status = "closed"
                elif status in {"failed", "deprecated"}:
                    gap.status = "open"
                else:
                    gap.status = "addressing"
                gap.updated_at = utc_now()
                if status == "promoted":
                    self.register_promoted_helper(
                        name=tool.name,
                        scope=tool.scope,
                        kind=tool.kind,
                        entrypoint=tool.entrypoint,
                        source_tool_id=tool.tool_id,
                        source_gap_category=gap.category,
                        validation_observation=tool.validation_observation,
                    )
                break
        self.save_session(session)
        return tool

    def load_promoted_helper_registry(self) -> list[PromotedHelperRecord]:
        if not self.registry_path.is_file():
            return []
        data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        return [PromotedHelperRecord(**item) for item in data.get("promoted_helpers", [])]

    def save_promoted_helper_registry(self, records: list[PromotedHelperRecord]) -> None:
        payload = {
            "promoted_helpers": [asdict(item) for item in records],
        }
        self.registry_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def register_promoted_helper(
        self,
        *,
        name: str,
        scope: str,
        kind: str,
        entrypoint: str,
        source_tool_id: str,
        source_gap_category: str | None,
        validation_observation: str | None,
    ) -> PromotedHelperRecord:
        records = self.load_promoted_helper_registry()
        existing = next((item for item in records if item.entrypoint == entrypoint or item.name == name), None)
        if existing is None:
            existing = PromotedHelperRecord(
                record_id=make_id("registry"),
                name=normalize_text(name),
                scope=normalize_text(scope),
                kind=normalize_text(kind),
                entrypoint=normalize_text(entrypoint),
                source_tool_id=source_tool_id,
                source_gap_category=source_gap_category,
                validation_observation=normalize_text(validation_observation or ""),
                usage_count=0,
                last_selected_at=None,
                status="promoted",
            )
            records.append(existing)
        else:
            existing.name = normalize_text(name)
            existing.scope = normalize_text(scope)
            existing.kind = normalize_text(kind)
            existing.entrypoint = normalize_text(entrypoint)
            existing.source_tool_id = source_tool_id
            existing.source_gap_category = source_gap_category
            existing.validation_observation = normalize_text(validation_observation or "")
            existing.status = "promoted"
            existing.updated_at = utc_now()
        self.save_promoted_helper_registry(records)
        return existing

    def close_capability_gap(self, session: KernelSession, gap_id: str, resolution: str) -> CapabilityGap:
        gap = next((item for item in session.capability_gaps if item.gap_id == gap_id), None)
        if gap is None:
            raise KeyError(f"gap not found: {gap_id}")
        gap.summary = normalize_text(f"{gap.summary} | resolution: {resolution}")[:400]
        gap.status = "closed"
        gap.updated_at = utc_now()
        self.save_session(session)
        return gap

    def _suggest_helper_tool_name(self, step: Step, suffix: str = "helper") -> str:
        base = re.sub(r"[^a-z0-9]+", "_", step.summary.lower()).strip("_")
        if not base:
            base = "task"
        return f"{base[:32]}_{suffix}"

    def _sync_task_and_intent_status(self, session: KernelSession, step: Step) -> None:
        task = next(task for task in session.tasks if task.task_id == step.parent_task_id)
        child_steps = [item for item in session.steps if item.parent_task_id == task.task_id]
        if all(item.status == "completed" for item in child_steps):
            task.status = "completed"
        elif any(item.status == "in_progress" for item in child_steps):
            task.status = "in_progress"
        elif any(item.status == "blocked" for item in child_steps):
            task.status = "blocked"
        else:
            task.status = "pending"
        task.updated_at = utc_now()
        intent = next(item for item in session.intents if item.intent_id == task.parent_intent_id)
        child_tasks = [item for item in session.tasks if item.parent_intent_id == intent.intent_id]
        if all(item.status == "completed" for item in child_tasks):
            intent.status = "completed"
        elif any(item.status == "in_progress" for item in child_tasks):
            intent.status = "in_progress"
        elif any(item.status == "blocked" for item in child_tasks):
            intent.status = "blocked"
        else:
            intent.status = "pending"
        intent.updated_at = utc_now()

    def render_summary(self, session: KernelSession) -> str:
        next_step = self.next_step(session)
        payload = {
            "session_id": session.session_id,
            "goal": session.goal.primary,
            "intent_count": len(session.intents),
            "task_count": len(session.tasks),
            "step_count": len(session.steps),
            "open_capability_gaps": len([gap for gap in session.capability_gaps if gap.status in {"open", "addressing"}]),
            "failure_pattern_count": len(session.failure_patterns),
            "helper_tool_count": len(session.helper_tools),
            "next_step": asdict(next_step) if next_step else None,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def list_reusable_helpers(self, session: KernelSession) -> list[HelperTool]:
        helpers = [tool for tool in session.helper_tools if tool.status in {"validated", "promoted"}]
        helpers.sort(key=lambda item: item.updated_at, reverse=True)
        return helpers

    def list_failure_patterns(self, session: KernelSession) -> list[FailurePattern]:
        patterns = list(session.failure_patterns)
        patterns.sort(key=lambda item: (item.occurrence_count, item.updated_at), reverse=True)
        return patterns


def emit_json(payload: str) -> None:
    try:
        sys.stdout.buffer.write(payload.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
    except Exception:
        print(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minimal durable kernel for goal-intent-task-step state.")
    parser.add_argument("--root", required=True, help="State root directory")
    sub = parser.add_subparsers(dest="command", required=True)

    new_session = sub.add_parser("new-session")
    new_session.add_argument("--prompt", required=True)
    new_session.add_argument("--channel", default="direct")
    new_session.add_argument("--user-id", default="unknown")

    show = sub.add_parser("show")
    show.add_argument("--session-id", required=True)

    ensure = sub.add_parser("ensure-session")
    ensure.add_argument("--prompt", required=True)
    ensure.add_argument("--channel", default="direct")
    ensure.add_argument("--user-id", default="unknown")

    record = sub.add_parser("record")
    record.add_argument("--session-id", required=True)
    record.add_argument("--step-id", required=True)
    record.add_argument("--observation", required=True)
    record.add_argument("--next-decision", required=True)
    record.add_argument("--status", required=True, choices=["pending", "in_progress", "completed", "blocked", "failed"])

    gap = sub.add_parser("analyze-gap")
    gap.add_argument("--session-id", required=True)
    gap.add_argument("--step-id", required=True)
    gap.add_argument("--observation", required=True)

    tool = sub.add_parser("register-tool")
    tool.add_argument("--session-id", required=True)
    tool.add_argument("--name", required=True)
    tool.add_argument("--scope", required=True)
    tool.add_argument("--kind", required=True)
    tool.add_argument("--entrypoint", required=True)
    tool.add_argument("--notes", required=True)
    tool.add_argument("--derived-from-gap-id")

    propose = sub.add_parser("propose-helper")
    propose.add_argument("--session-id", required=True)
    propose.add_argument("--gap-id", required=True)
    propose.add_argument("--kind", required=True)
    propose.add_argument("--entrypoint", required=True)
    propose.add_argument("--scope")
    propose.add_argument("--notes")

    validate = sub.add_parser("validate-tool")
    validate.add_argument("--session-id", required=True)
    validate.add_argument("--tool-id", required=True)
    validate.add_argument("--observation", required=True)
    validate.add_argument("--status", required=True, choices=["registered", "validated", "promoted", "failed", "deprecated"])

    close_gap = sub.add_parser("close-gap")
    close_gap.add_argument("--session-id", required=True)
    close_gap.add_argument("--gap-id", required=True)
    close_gap.add_argument("--resolution", required=True)

    helpers = sub.add_parser("list-helpers")
    helpers.add_argument("--session-id", required=True)

    patterns = sub.add_parser("list-patterns")
    patterns.add_argument("--session-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    kernel = AgentSocietyKernel(Path(args.root))
    if args.command == "new-session":
        session = kernel.bootstrap_session(args.prompt, args.channel, args.user_id)
        emit_json(kernel.render_summary(session))
        return 0
    if args.command == "show":
        session = kernel.load_session(args.session_id)
        emit_json(kernel.render_summary(session))
        return 0
    if args.command == "ensure-session":
        root = kernel.sessions_dir
        existing = sorted(root.glob("session_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        prompt = normalize_text(args.prompt)
        for path in existing[:20]:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("channel") == args.channel and data.get("user_id") == args.user_id and normalize_text(data.get("raw_request", "")) == prompt:
                session = kernel.load_session(data["session_id"])
                emit_json(kernel.render_summary(session))
                return 0
        session = kernel.bootstrap_session(args.prompt, args.channel, args.user_id)
        emit_json(kernel.render_summary(session))
        return 0
    if args.command == "record":
        session = kernel.load_session(args.session_id)
        kernel.record_observation(session, args.step_id, args.observation, args.next_decision, args.status)
        emit_json(kernel.render_summary(session))
        return 0
    if args.command == "analyze-gap":
        session = kernel.load_session(args.session_id)
        gap = kernel.analyze_capability_gap(session, args.step_id, args.observation)
        emit_json(json.dumps(asdict(gap), ensure_ascii=False, indent=2))
        return 0
    if args.command == "register-tool":
        session = kernel.load_session(args.session_id)
        tool = kernel.register_helper_tool(
            session,
            name=args.name,
            scope=args.scope,
            kind=args.kind,
            entrypoint=args.entrypoint,
            notes=args.notes,
            derived_from_gap_id=args.derived_from_gap_id,
        )
        emit_json(json.dumps(asdict(tool), ensure_ascii=False, indent=2))
        return 0
    if args.command == "propose-helper":
        session = kernel.load_session(args.session_id)
        tool = kernel.propose_helper_from_gap(
            session=session,
            gap_id=args.gap_id,
            kind=args.kind,
            entrypoint=args.entrypoint,
            scope=args.scope,
            notes=args.notes,
        )
        emit_json(json.dumps(asdict(tool), ensure_ascii=False, indent=2))
        return 0
    if args.command == "validate-tool":
        session = kernel.load_session(args.session_id)
        tool = kernel.validate_helper_tool(session, args.tool_id, args.observation, args.status)
        emit_json(json.dumps(asdict(tool), ensure_ascii=False, indent=2))
        return 0
    if args.command == "close-gap":
        session = kernel.load_session(args.session_id)
        gap = kernel.close_capability_gap(session, args.gap_id, args.resolution)
        emit_json(json.dumps(asdict(gap), ensure_ascii=False, indent=2))
        return 0
    if args.command == "list-helpers":
        session = kernel.load_session(args.session_id)
        payload = [asdict(item) for item in kernel.list_reusable_helpers(session)]
        emit_json(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "list-patterns":
        session = kernel.load_session(args.session_id)
        payload = [asdict(item) for item in kernel.list_failure_patterns(session)]
        emit_json(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
