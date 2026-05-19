#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import self_evolution_internal_repair as repair


def test_boundary_splits_internal_from_public_release():
    decision = repair.decide_boundary("内部能力补齐并推仓库，私人频道测试，通过后公共频道发布")
    assert decision.internal_write_allowed is True
    assert decision.private_verification_allowed is True
    assert decision.git_push_allowed is True
    assert decision.public_release_requires_approval is True
    assert decision.external_effect_requires_approval is False


def test_boundary_blocks_external_side_effects():
    decision = repair.decide_boundary("内部修复后真实取消预约并公开发布")
    assert decision.external_effect_requires_approval is True
    assert decision.git_push_allowed is False


def test_execute_run_writes_approval_package_and_does_not_push_on_verify_failure():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        command_result = repair.CommandResult(command="verify", returncode=1, stdout_tail="", stderr_tail="failed")
        with patch.object(repair, "run_command", return_value=command_result), patch.object(repair, "git_changed_files", return_value=[]):
            result = repair.execute_self_evolution_run(
                implementation_run_id="impl_test",
                text="落实内部能力后推仓库，内部实现后私人频道测试，通过后公共频道发布。",
                reason="requires autonomous internal repair",
                repo_root=repo,
                package_state_path=None,
                run_dir=Path(tmp) / "runs",
                verify_commands=["verify"],
                push=True,
            )
            assert result.status == "failed"
            assert result.stage == "verify_failed"
            assert result.pushed is False
            assert result.approval_package
            assert Path(result.approval_package).is_file(), result.approval_package
            approval = json.loads(Path(result.approval_package).read_text(encoding="utf-8"))
            assert approval["held_actions"]["public_release"] is True


def test_execute_run_can_reach_verified_without_push():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        command_result = repair.CommandResult(command="verify", returncode=0, stdout_tail="ok", stderr_tail="")
        with patch.object(repair, "run_command", return_value=command_result), patch.object(repair, "git_changed_files", return_value=[]):
            result = repair.execute_self_evolution_run(
                implementation_run_id="impl_ok",
                text="执行通用内部能力补齐并私人验证",
                reason="internal repair",
                repo_root=repo,
                package_state_path=None,
                run_dir=Path(tmp) / "runs",
                verify_commands=["verify"],
                push=False,
            )
    assert result.status == "passed"
    assert result.stage == "verified"
    assert result.retry_allowed is True


def test_verified_changed_run_commits_even_when_push_not_requested():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        command_result = repair.CommandResult(command="verify", returncode=0, stdout_tail="ok", stderr_tail="")
        changed_sequence = [["scripts/openclaw/example.py"], []]

        def fake_changed_files(_repo: Path) -> list[str]:
            return changed_sequence.pop(0) if changed_sequence else []

        def fake_run_command(command: str, _repo: Path) -> repair.CommandResult:
            assert "git push" not in command
            return command_result

        with (
            patch.object(repair, "run_command", side_effect=fake_run_command),
            patch.object(repair, "git_changed_files", side_effect=fake_changed_files),
            patch.object(
                repair.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(["git"], 0, stdout="abc123\n", stderr=""),
            ),
        ):
            result = repair.execute_self_evolution_run(
                implementation_run_id="impl_commit",
                text="执行通用内部能力补齐并私人验证",
                reason="internal repair",
                repo_root=repo,
                package_state_path=None,
                run_dir=Path(tmp) / "runs",
                verify_commands=["verify"],
                push=False,
            )
    assert result.status == "passed"
    assert result.stage == "committed"
    assert result.commit == "abc123"
    assert result.retry_allowed is True


def test_verified_changed_run_fails_without_commit_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        command_result = repair.CommandResult(command="verify", returncode=0, stdout_tail="ok", stderr_tail="")
        changed_sequence = [["scripts/openclaw/example.py"], ["scripts/openclaw/example.py"]]

        def fake_changed_files(_repo: Path) -> list[str]:
            return changed_sequence.pop(0) if changed_sequence else ["scripts/openclaw/example.py"]

        def fake_run_command(command: str, _repo: Path) -> repair.CommandResult:
            if command.startswith("git commit"):
                return repair.CommandResult(command=command, returncode=1, stdout_tail="", stderr_tail="nothing to commit")
            return command_result

        with patch.object(repair, "run_command", side_effect=fake_run_command), patch.object(repair, "git_changed_files", side_effect=fake_changed_files):
            result = repair.execute_self_evolution_run(
                implementation_run_id="impl_no_commit",
                text="执行通用内部能力补齐并私人验证",
                reason="internal repair",
                repo_root=repo,
                package_state_path=None,
                run_dir=Path(tmp) / "runs",
                verify_commands=["verify"],
                push=False,
            )
    assert result.status == "failed"
    assert result.stage == "commit_failed"
    assert result.retry_allowed is False
    assert "git evidence failed" in result.retry_reason


def test_verified_changed_run_blocks_undeclared_business_file_changes():
    package_state = {
        "package_id": "openclaw.repair_plan.openclaw_self_evolution_internal_repair",
        "files": {
            "runner": "scripts/openclaw/self_evolution_internal_repair.py",
            "test": "scripts/openclaw/test_self_evolution_internal_repair.py",
        },
    }
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        package_path = Path(tmp) / "package.json"
        package_path.write_text(json.dumps(package_state), encoding="utf-8")
        command_result = repair.CommandResult(command="verify", returncode=0, stdout_tail="ok", stderr_tail="")
        with patch.object(repair, "run_command", return_value=command_result), patch.object(repair, "git_changed_files", return_value=["scripts/weather/weather_image_forecast.py"]):
            result = repair.execute_self_evolution_run(
                implementation_run_id="impl_scope",
                text="执行通用内部能力补齐并私人验证",
                reason="internal repair",
                repo_root=repo,
                package_state_path=package_path,
                run_dir=Path(tmp) / "runs",
                verify_commands=["verify"],
                push=False,
            )
    assert result.status == "failed"
    assert result.stage == "change_scope_failed"
    assert result.retry_allowed is False
    assert "change scope violation" in result.evidence


def test_package_guardrail_text_does_not_create_false_external_block():
    package_state = {
        "llm_classification": {
            "autonomy_allowed": True,
            "autonomy_boundary": "Must not use credentials or perform external production side effects.",
            "missing_condition": "no public release or external production side effect was requested",
        },
        "allowed_repair_action": "autonomous_internal_repair",
    }
    decision = repair.decide_boundary(
        "完善增强能力并在私人频道测试",
        "registered tool returned non-zero exit code 2",
        package_state,
    )
    assert decision.internal_write_allowed is True
    assert decision.external_effect_requires_approval is False
    assert decision.public_release_requires_approval is False



def test_owner_private_test_package_allows_vague_original_request():
    package_state = {
        "allowed_repair_action": "autonomous_internal_repair",
        "permission_scope": "owner_dm_write",
        "llm_classification": {
            "intent_kind": "internal_self_evolution_private_test",
            "autonomy_allowed": True,
            "missing_condition": "private verification should proceed while public release stays gated",
        },
        "registry_tool": {
            "tool_id": "openclaw.self_evolution.internal_repair",
            "capability_id": "openclaw.self_evolution.internal_repair",
            "permission_scope": "owner_dm_write",
        },
    }
    decision = repair.decide_boundary(
        "那就在这里做一轮测试吧",
        "registered tool returned non-zero exit code 2",
        package_state,
    )
    assert decision.internal_write_allowed is True
    assert decision.private_verification_allowed is True
    assert decision.external_effect_requires_approval is False
    assert decision.public_release_requires_approval is False


def test_package_guardrail_text_keeps_public_release_approval_gated_without_blocking_private_verification():
    package_state = {
        "allowed_repair_action": "autonomous_internal_repair",
        "llm_classification": {
            "intent_kind": "internal_self_evolution_private_test",
            "autonomy_allowed": True,
            "autonomy_boundary": "Private verification allowed; public/channel release requires approval.",
        },
    }
    decision = repair.decide_boundary(
        "那就在这里做一轮测试吧",
        "registered tool returned non-zero exit code 2",
        package_state,
    )
    assert decision.internal_write_allowed is True
    assert decision.private_verification_allowed is True
    assert decision.public_release_requires_approval is False
    assert decision.external_effect_requires_approval is False


def test_registered_self_evolution_repair_package_action_allows_internal_repair():
    package_state = {
        "tool_id": "openclaw.repair_plan.openclaw_self_evolution_internal_repair",
        "permission_scope": "requires_authorization",
        "allowed_repair_action": "repair_binding_or_route_to_registered_tool_openclaw.self_evolution.internal_repair_then_privately_verify",
        "llm_classification": {
            "intent_kind": "internal_self_evolution_repair",
            "autonomy_allowed": True,
            "expected_capability_family": "openclaw.self_evolution.internal_repair",
            "allowed_repair_action": "repair_binding_or_route_to_registered_tool_openclaw.self_evolution.internal_repair_then_privately_verify",
            "autonomy_boundary": "Do not perform public release or external side effects without approval.",
        },
    }
    decision = repair.decide_boundary(
        "那你检查一下能力代码是不是有什么问题，请你修好它。",
        "Registered self repair tool semantically matches code inspection, repair, private verification, and verifiable completion requirements.",
        package_state,
    )
    assert decision.internal_write_allowed is True
    assert decision.private_verification_allowed is True
    assert decision.external_effect_requires_approval is False
    assert decision.public_release_requires_approval is False


def test_weather_rollout_package_allows_declared_domain_files_without_public_release_execution():
    package_state = {
        "tool_id": "openclaw.repair_plan.openclaw_self_evolution_internal_repair",
        "allowed_repair_action": "autonomous_internal_repair",
        "llm_classification": {
            "intent_kind": "update_formal_weather_cron_and_request_public_delivery",
            "autonomy_allowed": True,
            "expected_capability_family": "openclaw.self_evolution.internal_repair",
            "missing_condition": "formal weather cron workflow needs internal promotion while public release stays gated",
            "autonomy_boundary": "public-channel delivery requires approval",
        },
    }
    decision = repair.decide_boundary(
        "替换掉正式的每日7点的天气预报任务，投放给公共频道",
        "internal workflow update allowed; public delivery is scheduled/approval gated",
        package_state,
    )
    violations = repair.change_scope_violations(
        [
            "scripts/weather/weather_image_forecast.py",
            "scripts/remote_install_direct_discord_cron.py",
            "config/openclaw/intent_tools.json",
        ],
        package_state,
    )

    assert decision.internal_write_allowed is True
    assert decision.private_verification_allowed is True
    assert decision.public_release_requires_approval is True
    assert decision.external_effect_requires_approval is False
    assert violations == []


def test_public_release_text_is_not_hardcoded_business_rule():
    source = Path(repair.__file__).read_text(encoding="utf-8")
    assert "天气预报文" not in source
    assert "小红书" not in source


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print(f"{Path(__file__).name}: ok")
