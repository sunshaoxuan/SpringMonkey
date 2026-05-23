from __future__ import annotations

import json
import tempfile
from pathlib import Path

import capability_repair_runner
import regression_repair_runner as runner
from harness_intent_agent import IntentFrame


def test_write_baseline_regression_allows_internal_repair() -> None:
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
    assert result.status == "internal_repair_required"
    assert result.expected_tool_id == "timescar.dm.adjust_start"
    assert result.write_operation is True
    row = json.loads(rows[0])
    assert row["deployment_policy"] == "auto_internal_repair_external_replay_gated"
    assert row["internal_repair_allowed"] is True
    assert row["external_side_effect"] is True


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
            implementation_starter=lambda **_kwargs: capability_repair_runner.DomainImplementationRun(
                run_id="impl_regression",
                package_id="regression_test",
                status="running",
                stage="implementation_agent_running",
                job_name="自增益实现",
                started_at="2026-05-23T00:00:00+00:00",
                pid=123,
                prompt_file="prompt.txt",
                stdout_file="stdout.log",
                stderr_file="stderr.log",
                long_task_id="long_regression",
                evidence="test_started",
            ),
        )
        events = [json.loads(line) for line in Path(result.event_log).read_text(encoding="utf-8").splitlines()]
    assert result.status == "repair_started"
    assert result.replay_allowed is False
    assert result.gap_ref.startswith("regression_ref=")
    assert result.implementation_run["run_id"] == "impl_regression"
    assert events[-1]["baseline_case_id"] == "timescar_adjust_relative_this_booking"
    assert events[-1]["regression_type"] == "existing_tool_regression"
    assert events[-1]["resolved_by"]["implementation_run"]["run_id"] == "impl_regression"


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


def test_family_match_is_known_direction_repair_without_exact_text(monkeypatch) -> None:
    def fake_frame(text: str, *, context: str, registry: dict, timeout: int = 30, model_caller=None) -> IntentFrame:
        return IntentFrame(
            conversation_mode="task",
            domain="self",
            action="status",
            canonical_text=text,
            context_refs=[],
            parameters={},
            safety="readonly",
            result_contract={"type": "self_evolution_status"},
            tool_candidates=[{"tool_id": "openclaw.self_evolution.status", "confidence": 0.95, "reason": "test"}],
            confidence=0.95,
            reason="test family frame",
            source="test",
        )

    monkeypatch.setattr("verify_capability_baseline.infer_intent_frame", fake_frame)
    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_regression_repair(
            text="列出最近能力回归。",
            stage="binding",
            reason="tool binding gap",
            kernel_root=Path(tmp) / "kernel",
        )

    assert result.matched is True
    assert result.match_kind == "capability_family"
    assert result.regression_type == "known_direction_repair"
    assert result.baseline_case_id == "self_evolution_status"
    assert result.status == "verified"
    assert result.package["risk_level"] == "auto_safe_readonly"
    assert result.package["original_text"] == "列出最近能力回归。"


def test_reference_tools_inherit_same_family_contract() -> None:
    registry = {
        "tools": [
            {
                "tool_id": "self.reference",
                "domain": "self",
                "actions": ["status"],
                "permission_scope": "owner_dm_readonly",
                "write_operation": False,
                "entrypoint": "scripts/openclaw/self_evolution_status.py",
                "safety": "readonly",
            },
            {
                "tool_id": "self.write",
                "domain": "self",
                "actions": ["status"],
                "permission_scope": "owner_dm_write",
                "write_operation": True,
                "entrypoint": "scripts/openclaw/write.py",
                "safety": "write",
            },
        ]
    }

    refs = runner.find_reference_tools(
        registry,
        {"domain": "self", "action": "status", "safety": "readonly", "write_operation": False},
    )

    assert refs[0]["tool_id"] == "self.reference"
    assert all(ref["write_operation"] is False for ref in refs)
