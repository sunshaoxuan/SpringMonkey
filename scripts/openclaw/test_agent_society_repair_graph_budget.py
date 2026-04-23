#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path
import re

from agent_society_kernel import AgentSocietyKernel


def _promote(
    kernel: AgentSocietyKernel,
    session,
    step_id: str,
    observation: str,
    entrypoint: str,
    category: str,
    workflow_steps: list[str],
) -> None:
    kernel.record_observation(session, step_id, observation, "classify repairer", "blocked")
    session = kernel.load_session(session.session_id)
    gap = kernel.analyze_capability_gap(session, step_id, observation)
    session = kernel.load_session(session.session_id)
    tool = kernel.propose_helper_from_gap(
        session,
        gap.gap_id,
        "script",
        entrypoint,
        scope=category,
        notes=gap.proposed_repair,
    )
    session = kernel.load_session(session.session_id)
    kernel.validate_helper_tool(
        session,
        tool.tool_id,
        observation=json.dumps(
            {
                "status": "ready",
                "category": category,
                "contract": {
                    "helper_name": tool.name,
                    "purpose": gap.proposed_repair,
                    "purpose_hash": f"hash-{category}-{entrypoint}",
                    "category": category,
                },
                "checks": [{"kind": "path_exists", "ok": True}],
                "suggested_actions": ["act"],
                "repair_workflow": [{"step": item, "action": item} for item in workflow_steps],
                "drift": {"ok": True, "reasons": [], "purpose_hash": f"hash-{category}-{entrypoint}"},
            },
            ensure_ascii=False,
        ),
        status="promoted",
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agent_society_repair_graph_budget_") as tmp:
        root = Path(tmp)
        kernel = AgentSocietyKernel(root)

        seeds = [
            (
                "Investigate timeout failures.",
                "timeout while waiting for first response",
                "scripts/openclaw/helpers/timeout_probe.py",
                "runtime_timeout",
                ["classify timeout surface", "verify timeout guard", "apply bounded repair"],
            ),
            (
                "Investigate runtime drift failures.",
                "bundle patch drift after upgrade",
                "scripts/openclaw/helpers/runtime_bundle_probe.py",
                "runtime_drift",
                ["identify active artifact", "check expected anchor contract", "repair active target only"],
            ),
            (
                "Investigate missing tool failures.",
                "missing tool for direct visibility watchdog",
                "scripts/openclaw/helpers/watchdog_probe.py",
                "tool_missing",
                ["identify missing capability", "generate bounded helper", "validate helper output"],
            ),
            (
                "Investigate execution blocked failures.",
                "no response generated after direct task execution",
                "scripts/openclaw/helpers/direct_unblock_probe.py",
                "execution_blocked",
                ["classify block layer", "pick narrow repair path", "verify unblock"],
            ),
        ]

        for prompt, observation, entrypoint, category, workflow in seeds:
            session = kernel.bootstrap_session(prompt, channel="line", user_id=f"seed-{category}")
            step = kernel.next_step(session)
            if step is None:
                raise AssertionError(f"expected seed step for {category}")
            _promote(kernel, session, step.step_id, observation, entrypoint, category, workflow)

        composed = kernel.bootstrap_session(
            "The cron timed out after an upgrade, the bundle patch may have drifted, and the direct watchdog helper looks missing. Please repair the runtime and report back.",
            channel="cron:line",
            user_id="timescar-ask-cancel-next24h-0700",
        )
        next_step = kernel.next_step(composed)
        if next_step is None:
            raise AssertionError("expected composed next step")
        if "repair graph budget:" not in next_step.next_decision:
            raise AssertionError(f"expected budget note, got {next_step.next_decision}")
        if "rollback policy:" not in next_step.next_decision:
            raise AssertionError(f"expected rollback note, got {next_step.next_decision}")
        match = re.search(r"repair graph budget: max (\d+) repairers", next_step.next_decision)
        if not match:
            raise AssertionError(f"expected bounded repairer count, got {next_step.next_decision}")
        if int(match.group(1)) < 1 or int(match.group(1)) > 3:
            raise AssertionError(f"expected repairer budget between 1 and 3, got {next_step.next_decision}")
        if "rollback evidence" not in next_step.expected_observation.lower():
            raise AssertionError(f"expected rollback evidence requirement, got {next_step.expected_observation}")
        payload = {
            "chosen_tool": next_step.chosen_tool,
            "tool_candidates": next_step.tool_candidates[:5],
            "next_decision": next_step.next_decision,
            "expected_observation": next_step.expected_observation,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
