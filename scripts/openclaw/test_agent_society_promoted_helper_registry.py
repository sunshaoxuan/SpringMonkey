#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agent_society_kernel import AgentSocietyKernel


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agent_society_helper_registry_") as tmp:
        root = Path(tmp)
        kernel = AgentSocietyKernel(root)

        session = kernel.bootstrap_session(
            "Please investigate the timeout issue and fix it.",
            channel="line",
            user_id="tester",
        )
        step = kernel.next_step(session)
        if step is None:
            raise AssertionError("expected initial step")
        kernel.record_observation(session, step.step_id, "timeout while waiting for first response", "classify timeout gap", "blocked")
        session = kernel.load_session(session.session_id)
        gap = kernel.analyze_capability_gap(session, step.step_id, "timeout while waiting for first response")
        session = kernel.load_session(session.session_id)
        tool = kernel.propose_helper_from_gap(
            session,
            gap.gap_id,
            "script",
            "scripts/openclaw/helpers/timeout_probe.py",
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

        registry = kernel.load_promoted_helper_registry()
        if len(registry) != 1:
            raise AssertionError(f"expected one promoted helper record, got {len(registry)}")
        if registry[0].entrypoint != "scripts/openclaw/helpers/timeout_probe.py":
            raise AssertionError(f"unexpected registry entrypoint: {registry[0].entrypoint}")

        fresh = kernel.bootstrap_session(
            "The cron timed out again before first response, please investigate.",
            channel="cron:line",
            user_id="timescar-ask-cancel-next24h-0700",
        )
        fresh_step = kernel.next_step(fresh)
        if fresh_step is None:
            raise AssertionError("expected next step in fresh session")
        if fresh_step.chosen_tool != "scripts/openclaw/helpers/timeout_probe.py":
            raise AssertionError(f"expected promoted registry helper to be chosen, got {fresh_step.chosen_tool}")

        registry_after = kernel.load_promoted_helper_registry()
        payload = {
            "registry_count": len(registry_after),
            "chosen_tool": fresh_step.chosen_tool,
            "usage_count": registry_after[0].usage_count,
        }
        if registry_after[0].usage_count < 1:
            raise AssertionError(f"expected registry usage_count >= 1, got {registry_after[0].usage_count}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
