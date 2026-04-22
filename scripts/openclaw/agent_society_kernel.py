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


class AgentSocietyKernel:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.sessions_dir = root / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

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
        )

    def next_step(self, session: KernelSession) -> Step | None:
        pending_steps = [step for step in session.steps if step.status in {"pending", "in_progress"}]
        if not pending_steps:
            return None
        task_order = {task.task_id: index for index, task in enumerate(session.tasks)}
        pending_steps.sort(key=lambda step: task_order.get(step.parent_task_id, 10**6))
        return pending_steps[0]

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
            "next_step": asdict(next_step) if next_step else None,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


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

    record = sub.add_parser("record")
    record.add_argument("--session-id", required=True)
    record.add_argument("--step-id", required=True)
    record.add_argument("--observation", required=True)
    record.add_argument("--next-decision", required=True)
    record.add_argument("--status", required=True, choices=["pending", "in_progress", "completed", "blocked", "failed"])
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
    if args.command == "record":
        session = kernel.load_session(args.session_id)
        kernel.record_observation(session, args.step_id, args.observation, args.next_decision, args.status)
        emit_json(kernel.render_summary(session))
        return 0
    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
