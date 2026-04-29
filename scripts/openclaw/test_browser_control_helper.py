#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from agent_society_kernel import AgentSocietyKernel
from helpers.browser_cdp_human import choose_tab, is_headless_like


def test_browser_helper_utilities() -> None:
    tabs = [
        {"id": "blank", "url": "about:blank", "title": ""},
        {"id": "live", "url": "https://accounts.google.com/signup", "title": "Create your Google Account"},
    ]
    assert choose_tab(tabs, "latest")["id"] == "live"
    assert choose_tab(tabs, "accounts.google.com")["id"] == "live"
    assert is_headless_like("Mozilla/5.0 HeadlessChrome/146", []) is True
    assert is_headless_like("Mozilla/5.0 Chrome/146", ["--remote-debugging-port=18800"]) is False


def test_browser_control_gap_routes_to_cdp_helper() -> None:
    with tempfile.TemporaryDirectory(prefix="browser_control_kernel_") as tmp:
        kernel = AgentSocietyKernel(Path(tmp))
        session = kernel.bootstrap_session(
            "Use the real host browser to register an account and recover if targetId drifts.",
            channel="discord",
            user_id="tester",
        )
        step = kernel.next_step(session)
        assert step is not None
        gap = kernel.analyze_capability_gap(
            session,
            step.step_id,
            "browser failed: action targetId must match request targetId; tab not found; headless fallback claim",
        )
        assert gap.category == "browser_control"
        assert gap.proposed_tool_name == "browser_cdp_human"
        tool = kernel.propose_helper_from_gap(
            kernel.load_session(session.session_id),
            gap.gap_id,
            "script",
            "scripts/openclaw/helpers/browser_cdp_human.py",
            scope="browser_control",
            notes=gap.proposed_repair,
        )
        payload = {
            "contract": {"category": "browser_control"},
            "repair_workflow": [
                {"step": "prove browser substrate", "action": "run helper status"},
                {"step": "reselect live target", "action": "avoid stale target ids"},
            ],
            "drift": {"ok": True, "reasons": []},
        }
        session = kernel.load_session(session.session_id)
        kernel.validate_helper_tool(session, tool.tool_id, json.dumps(payload), "promoted")
        fresh = kernel.bootstrap_session(
            "Register a Google account using the real host browser.",
            channel="discord",
            user_id="tester",
        )
        fresh_step = kernel.next_step(fresh)
        assert fresh_step is not None
        assert fresh_step.chosen_tool == "scripts/openclaw/helpers/browser_cdp_human.py"


def test_helper_help_runs() -> None:
    helper = Path(__file__).resolve().parent / "helpers" / "browser_cdp_human.py"
    proc = subprocess.run([sys.executable, str(helper), "--help"], text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr
    assert "Human-style CDP control" in proc.stdout


def main() -> int:
    test_browser_helper_utilities()
    test_browser_control_gap_routes_to_cdp_helper()
    test_helper_help_runs()
    print("browser_control_helper_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
