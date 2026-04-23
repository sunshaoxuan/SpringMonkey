#!/usr/bin/env python3
from __future__ import annotations

from upsert_generic_cron_job import (
    JOB_ORCHESTRATOR_MARKER,
    TASK_CREATION_MARKER,
    apply_task_creation_policy,
)


def main() -> int:
    weather_message = "每天早上抓取天气，翻译成中文，整理成报告后发到 Discord。"
    wrapped, depth = apply_task_creation_policy(weather_message, requested_depth="auto")
    if depth != "staged":
        raise AssertionError(f"expected staged depth, got {depth!r}")
    if TASK_CREATION_MARKER not in wrapped or "User scheduled task:" not in wrapped:
        raise AssertionError("expected staged task policy wrapper")
    if "execution_depth: staged" not in wrapped:
        raise AssertionError("expected staged execution depth marker")
    if JOB_ORCHESTRATOR_MARKER not in wrapped:
        raise AssertionError("expected staged job to include orchestrator policy")

    agentic_message = "每天检查失败的任务，自己写工具并调试上线新工具，不断增强自己的能力。"
    wrapped, depth = apply_task_creation_policy(agentic_message, requested_depth="auto")
    if depth != "agentic":
        raise AssertionError(f"expected agentic depth, got {depth!r}")
    if "execution_depth: agentic" not in wrapped:
        raise AssertionError("expected agentic execution depth marker")
    if JOB_ORCHESTRATOR_MARKER not in wrapped:
        raise AssertionError("expected agentic job to include orchestrator policy")

    atomic_message = "echo hello"
    wrapped, depth = apply_task_creation_policy(atomic_message, requested_depth="auto")
    if depth != "atomic" or wrapped != atomic_message:
        raise AssertionError("expected atomic messages to remain unwrapped")

    wrapped, depth = apply_task_creation_policy(atomic_message, requested_depth="auto", orchestrator_mode="required")
    if depth != "atomic" or JOB_ORCHESTRATOR_MARKER not in wrapped:
        raise AssertionError("expected required orchestrator mode to wrap atomic messages")

    wrapped, depth = apply_task_creation_policy(weather_message, requested_depth="auto", orchestrator_mode="off")
    if JOB_ORCHESTRATOR_MARKER in wrapped:
        raise AssertionError("expected orchestrator mode off to skip orchestrator policy")

    existing_message = f"{TASK_CREATION_MARKER}\nexecution_depth: staged\n\nhello"
    wrapped, depth = apply_task_creation_policy(existing_message, requested_depth="auto")
    if wrapped != existing_message:
        raise AssertionError("expected existing policy wrapper to remain unchanged")

    print("upsert_generic_cron_job_policy_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
