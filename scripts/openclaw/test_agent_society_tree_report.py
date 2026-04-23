#!/usr/bin/env python3
from __future__ import annotations

import tempfile
from pathlib import Path

from agent_society_kernel import AgentSocietyKernel
from job_orchestrator import build_session_request


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agent_society_tree_") as tmp:
        kernel = AgentSocietyKernel(Path(tmp))
        request = build_session_request(
            job_name="timescar-daily-report-2200",
            category="timescar",
            prompt="Fetch TimesCar reservations, render a Chinese daily report, and preserve delivery output.",
            command=["python3", "scripts/timescar_daily_report_render.py"],
        )
        session = kernel.bootstrap_session(request, channel="cron:timescar-daily-report-2200", user_id="test")
        assert len(session.intents) == 1
        assert len(session.tasks) == 3
        assert len(session.steps) == 3
        assert session.tasks[0].status == "completed"
        assert session.intents[0].reason_to_exist == "Fetch TimesCar reservations, render a Chinese daily report, and preserve delivery output."
        action_step = next(step for step in session.steps if step.action_kind == "tool")
        assert action_step.depends_on
        assert action_step.shared_context_keys == [
            "cron_job",
            "job:timescar-daily-report-2200",
            "category:timescar",
            "workspace",
        ]
        report = kernel.render_tree_report(session)
        assert "Goal [active]" in report
        assert "Intent 1" in report
        assert "Fetch TimesCar reservations, render a Chinese daily report" in report
        assert "Run timescar-daily-report-2200 under orchestrated execution semantics" not in report
        assert "Task 2" in report
        assert "context=cron_job,job:timescar-daily-report-2200,category:timescar,workspace" in report
        assert "depends_on=1" in report
        print("agent_society_tree_report_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
