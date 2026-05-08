from __future__ import annotations

import json
import tempfile
from pathlib import Path

import capability_repair_runner
import regression_repair_runner as runner


def test_write_baseline_regression_waits_for_authorization() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_regression_repair(
            text="把这单的开始时间往后推24小时，结束时间不变。",
            stage="binding",
            reason="no registered tool for IntentFrame domain/action: timescar/adjust",
            kernel_root=Path(tmp) / "kernel",
        )
        rows = (Path(tmp) / "kernel" / "regression_repair_packages.jsonl").read_text(encoding="utf-8").splitlines()
    assert result.matched is True
    assert result.regression_type == "existing_tool_regression"
    assert result.status == "awaiting_authorization"
    assert result.expected_tool_id == "timescar.dm.adjust_start"
    assert result.write_operation is True
    assert json.loads(rows[0])["deployment_policy"] == "await_explicit_authorization"


def test_readonly_baseline_regression_is_verified_package() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_regression_repair(
            text="检查自演进状态。",
            stage="binding",
            reason="tool binding gap",
            kernel_root=Path(tmp) / "kernel",
        )
    assert result.matched is True
    assert result.status == "verified"
    assert result.write_operation is False
    assert result.package["deployment_policy"] == "auto_deploy_after_verify"


def test_capability_repair_prefers_baseline_regression_over_new_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = capability_repair_runner.run_repair(
            text="把这单的开始时间往后推24小时，结束时间不变。",
            channel="discord_dm",
            user_id="999666719356354610",
            stage="binding",
            reason="tool binding gap",
            kernel_root=Path(tmp) / "kernel",
            repo_root=Path(__file__).resolve().parents[2],
        )
        events = [json.loads(line) for line in Path(result.event_log).read_text(encoding="utf-8").splitlines()]
    assert result.status == "awaiting_authorization"
    assert result.replay_allowed is False
    assert result.gap_ref.startswith("regression_ref=")
    assert events[-1]["baseline_case_id"] == "timescar_adjust_relative_this_booking"
    assert events[-1]["regression_type"] == "existing_tool_regression"


def test_capability_repair_allows_readonly_baseline_regression_replay() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = capability_repair_runner.run_repair(
            text="检查自演进状态。",
            channel="discord_dm",
            user_id="999666719356354610",
            stage="binding",
            reason="tool binding gap",
            kernel_root=Path(tmp) / "kernel",
            repo_root=Path(__file__).resolve().parents[2],
        )
    assert result.status == "verified"
    assert result.replay_allowed is True
    assert result.registry_tool is None
    assert result.toolsmith_package["status"] == "verified"
