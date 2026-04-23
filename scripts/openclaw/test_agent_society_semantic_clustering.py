#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agent_society_kernel import AgentSocietyKernel


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agent_society_semantic_cluster_") as tmp:
        root = Path(tmp)
        kernel = AgentSocietyKernel(root)
        session = kernel.bootstrap_session(
            "Please keep checking the runtime timeout issue and report progress.",
            channel="line",
            user_id="tester",
        )
        step = kernel.next_step(session)
        if step is None:
            raise AssertionError("expected active step")

        observations = [
            "cron job execution timed out while waiting for first response",
            "ETIMEDOUT: stalled before first token arrived",
            "task hung with no visible progress output",
        ]
        signatures: list[str] = []
        statuses: list[str] = []
        for observation in observations:
            kernel.record_observation(session, step.step_id, observation, "classify timeout cluster", "blocked")
            session = kernel.load_session(session.session_id)
            gap = kernel.analyze_capability_gap(session, step.step_id, observation)
            session = kernel.load_session(session.session_id)
            matched = [item for item in kernel.list_failure_patterns(session) if gap.gap_id in item.example_gap_ids]
            if len(matched) != 1:
                raise AssertionError(f"expected exactly one matched pattern, got {len(matched)}")
            signatures.append(matched[0].signature)
            statuses.append(matched[0].status)

        if len(set(signatures)) != 1:
            raise AssertionError(f"expected one stable semantic signature, got {signatures}")
        if statuses != ["candidate", "emerging", "learned"]:
            raise AssertionError(f"unexpected lifecycle progression: {statuses}")

        payload = {
            "signature": signatures[0],
            "statuses": statuses,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
