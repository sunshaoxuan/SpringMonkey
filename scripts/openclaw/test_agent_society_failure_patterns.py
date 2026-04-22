#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agent_society_kernel import AgentSocietyKernel


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agent_society_pattern_test_") as tmp:
        root = Path(tmp)
        kernel = AgentSocietyKernel(root)
        session = kernel.bootstrap_session(
            "please handle the direct task and report back",
            channel="line",
            user_id="tester",
        )
        step = kernel.next_step(session)
        if step is None:
            raise AssertionError("expected an active step")

        observations = [
            "timeout while waiting for first response",
            "timed out again while waiting for first response",
            "timeout while waiting for first response once more",
        ]

        statuses: list[str] = []
        signature: str | None = None
        for observation in observations:
            kernel.record_observation(session, step.step_id, observation, "classify timeout pattern", "blocked")
            session = kernel.load_session(session.session_id)
            gap = kernel.analyze_capability_gap(session, step.step_id, observation)
            session = kernel.load_session(session.session_id)
            patterns = kernel.list_failure_patterns(session)
            matched = [item for item in patterns if gap.gap_id in item.example_gap_ids]
            if len(matched) != 1:
                raise AssertionError(f"expected one matched failure pattern, got {len(matched)}")
            if signature is None:
                signature = matched[0].signature
            elif matched[0].signature != signature:
                raise AssertionError(f"expected stable failure signature {signature}, got {matched[0].signature}")
            statuses.append(matched[0].status)

        payload = {
            "statuses": statuses,
            "pattern_count": len(kernel.list_failure_patterns(session)),
            "final_pattern": json.loads(json.dumps(kernel.list_failure_patterns(session)[0], default=lambda o: o.__dict__)),
        }

        if statuses != ["candidate", "emerging", "learned"]:
            raise AssertionError(f"unexpected pattern lifecycle: {statuses}")
        if payload["final_pattern"]["occurrence_count"] != 3:
            raise AssertionError(f"expected occurrence_count=3, got {payload['final_pattern']['occurrence_count']}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
