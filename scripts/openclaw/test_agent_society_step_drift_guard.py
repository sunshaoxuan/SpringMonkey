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
    drift_ok: bool,
    drift_reasons: list[str],
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
                "repair_workflow": [{"step": "probe", "action": "probe"}],
                "drift": {"ok": drift_ok, "reasons": drift_reasons, "purpose_hash": f"hash-{category}"},
            },
            ensure_ascii=False,
        ),
        status="promoted",
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agent_society_step_drift_guard_") as tmp:
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
            True,
            [],
        )

        drifted_session = kernel.bootstrap_session(
            "Investigate runtime drift failures.",
            channel="line",
            user_id="tester-drifted",
        )
        drifted_step = kernel.next_step(drifted_session)
        if drifted_step is None:
            raise AssertionError("expected drift step")
        _promote(
            kernel,
            drifted_session,
            drifted_step.step_id,
            "bundle patch drift after upgrade",
            "scripts/openclaw/helpers/runtime_bundle_probe.py",
            "runtime_drift",
            False,
            ["helper drift guard is already marked not ok"],
        )

        composed = kernel.bootstrap_session(
            "The cron timed out after an upgrade. Please repair the runtime and report back.",
            channel="cron:line",
            user_id="timescar-ask-cancel-next24h-0700",
        )
        next_step = kernel.next_step(composed)
        if next_step is None:
            raise AssertionError("expected next step")
        if "scripts/openclaw/helpers/timeout_probe.py" not in next_step.tool_candidates:
            raise AssertionError(f"expected timeout helper in candidates, got {next_step.tool_candidates}")
        if "scripts/openclaw/helpers/runtime_bundle_probe.py" in next_step.tool_candidates:
            raise AssertionError(f"drifted helper should have been filtered, got {next_step.tool_candidates}")
        if "drift guard filtered repairers:" not in next_step.next_decision:
            raise AssertionError(f"expected drift guard note in next_decision, got {next_step.next_decision}")
        payload = {
            "chosen_tool": next_step.chosen_tool,
            "tool_candidates": next_step.tool_candidates[:4],
            "next_decision": next_step.next_decision,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
