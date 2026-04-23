#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

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
                    "purpose_hash": f"hash-{category}",
                    "category": category,
                },
                "checks": [{"kind": "path_exists", "ok": True}],
                "suggested_actions": ["act"],
                "repair_workflow": [{"step": item, "action": item} for item in workflow_steps],
                "drift": {"ok": True, "reasons": [], "purpose_hash": f"hash-{category}"},
            },
            ensure_ascii=False,
        ),
        status="promoted",
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agent_society_composed_repairers_") as tmp:
        root = Path(tmp)
        kernel = AgentSocietyKernel(root)

        timeout_session = kernel.bootstrap_session(
            "Investigate timeout failures.",
            channel="line",
            user_id="tester-timeout",
        )
        timeout_step = kernel.next_step(timeout_session)
        if timeout_step is None:
            raise AssertionError("expected timeout step")
        _promote(
            kernel,
            timeout_session,
            timeout_step.step_id,
            "timeout while waiting for first response",
            "scripts/openclaw/helpers/timeout_probe.py",
            "runtime_timeout",
            ["classify timeout surface", "verify timeout guard", "apply bounded repair"],
        )

        drift_session = kernel.bootstrap_session(
            "Investigate runtime drift failures.",
            channel="line",
            user_id="tester-drift",
        )
        drift_step = kernel.next_step(drift_session)
        if drift_step is None:
            raise AssertionError("expected drift step")
        _promote(
            kernel,
            drift_session,
            drift_step.step_id,
            "bundle patch drift after upgrade",
            "scripts/openclaw/helpers/runtime_bundle_probe.py",
            "runtime_drift",
            ["identify active artifact", "check expected anchor contract", "repair active target only"],
        )

        composed = kernel.bootstrap_session(
            "The cron timed out after an upgrade and the bundle patch may have drifted. Please repair the runtime and report back.",
            channel="cron:line",
            user_id="timescar-ask-cancel-next24h-0700",
        )
        next_step = kernel.next_step(composed)
        if next_step is None:
            raise AssertionError("expected composed next step")
        if "scripts/openclaw/helpers/timeout_probe.py" not in next_step.tool_candidates:
            raise AssertionError(f"missing timeout repairer from candidates: {next_step.tool_candidates}")
        if "scripts/openclaw/helpers/runtime_bundle_probe.py" not in next_step.tool_candidates:
            raise AssertionError(f"missing drift repairer from candidates: {next_step.tool_candidates}")
        if "compose repairers in order:" not in next_step.next_decision:
            raise AssertionError(f"expected composed plan in next_decision, got {next_step.next_decision}")
        if "timeout" not in next_step.next_decision.lower() or "anchor" not in next_step.next_decision.lower():
            raise AssertionError(f"expected both repairer plans in next_decision, got {next_step.next_decision}")
        payload = {
            "chosen_tool": next_step.chosen_tool,
            "tool_candidates": next_step.tool_candidates[:4],
            "next_decision": next_step.next_decision,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
