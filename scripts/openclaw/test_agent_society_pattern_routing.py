#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agent_society_kernel import AgentSocietyKernel


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agent_society_pattern_routing_") as tmp:
        root = Path(tmp)
        kernel = AgentSocietyKernel(root)
        session = kernel.bootstrap_session(
            "Please investigate the cron timeout failure, repair it, and report the result.",
            "cron:line",
            "timescar-ask-cancel-next24h-0700",
        )
        step = kernel.next_step(session)
        if step is None:
            raise AssertionError("expected initial step")
        observations = [
            "cron job timed out while waiting for first response",
            "cron job timed out while waiting for first response",
            "cron job timed out while waiting for first response",
        ]
        for observation in observations:
            kernel.record_observation(session, step.step_id, observation, "classify timeout pattern", "blocked")
            gap = kernel.analyze_capability_gap(session, step.step_id, observation)
            session = kernel.load_session(session.session_id)
            tool = kernel.propose_helper_from_gap(
                session,
                gap.gap_id,
                "script",
                "scripts/openclaw/helpers/cron_timeout_probe.py",
                scope=gap.category,
                notes=gap.proposed_repair,
            )
            session = kernel.load_session(session.session_id)
            kernel.validate_helper_tool(
                session,
                tool.tool_id,
                observation='{"status":"ready","category":"runtime_timeout","checks":[1]}',
                status="promoted",
            )
            session = kernel.load_session(session.session_id)

        next_step = kernel.next_step(session)
        if next_step is None:
            raise AssertionError("expected next step after learned pattern")
        patterns = kernel.list_failure_patterns(session)
        if patterns[0].status != "learned":
            raise AssertionError(f"expected learned pattern, got {patterns[0].status}")
        if next_step.chosen_tool != "scripts/openclaw/helpers/cron_timeout_probe.py":
            raise AssertionError(f"expected chosen_tool to prefer learned helper, got {next_step.chosen_tool}")
        if "prefer learned repair path" not in next_step.next_decision:
            raise AssertionError(f"expected learned routing note in next_decision, got {next_step.next_decision}")
        payload = {
            "pattern_status": patterns[0].status,
            "chosen_tool": next_step.chosen_tool,
            "next_decision": next_step.next_decision,
            "tool_candidates": next_step.tool_candidates[:3],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
