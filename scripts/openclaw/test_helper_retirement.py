#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agent_society_kernel import AgentSocietyKernel


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agent_society_helper_retirement_") as tmp:
        kernel = AgentSocietyKernel(Path(tmp))
        record = kernel.register_promoted_helper(
            name="stale_runtime_drift_helper",
            scope="runtime_drift",
            kind="script",
            entrypoint="scripts/openclaw/helpers/stale_runtime_drift_helper.py",
            source_tool_id="tool_stale",
            source_gap_category="runtime_drift",
            validation_observation="{}",
            helper_contract={"category": "runtime_drift"},
            repair_workflow=[{"step": "probe", "action": "probe"}],
            drift={"ok": False, "reasons": ["stale bundle anchor"]},
        )
        for idx in range(3):
            session = kernel.bootstrap_session(
                f"Handle runtime drift failure after bundle upgrade {idx}",
                channel="cron:test",
                user_id=f"job-{idx}",
            )
            step = kernel.next_step(session)
            if step is None:
                raise AssertionError("expected next step")
            if record.entrypoint in step.tool_candidates:
                raise AssertionError("drifted helper should not be selected")
        registry = kernel.load_promoted_helper_registry()
        updated = next(item for item in registry if item.record_id == record.record_id)
        if updated.status != "deprecated":
            raise AssertionError(f"expected deprecated helper, got {updated.status}")
        if updated.drift_reject_count < 3:
            raise AssertionError(f"expected reject count >= 3, got {updated.drift_reject_count}")

        session = kernel.bootstrap_session(
            "runtime drift after bundle upgrade",
            channel="cron:test",
            user_id="job-after-deprecated",
        )
        step = kernel.next_step(session)
        if step is None:
            raise AssertionError("expected next step after deprecation")
        if record.entrypoint in step.tool_candidates:
            raise AssertionError("deprecated helper must not be reused")
        print(json.dumps({"helper_status": updated.status, "rejects": updated.drift_reject_count}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
