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
        with patch.object(repair, "run_command", return_value=command_result), patch.object(repair, "git_changed_files", return_value=["x.py"]):
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


def test_public_release_text_is_not_hardcoded_business_rule():
    source = Path(repair.__file__).read_text(encoding="utf-8")
    assert "天气预报文" not in source
    assert "小红书" not in source


def test_verified_changed_run_commits_even_when_push_not_requested():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        calls: list[str] = []

        def fake_run(command: str, repo_root: Path) -> repair.CommandResult:
            calls.append(command)
            if command == "verify":
                return repair.CommandResult(command=command, returncode=0, stdout_tail="ok", stderr_tail="")
            if command == "git add -A":
                return repair.CommandResult(command=command, returncode=0, stdout_tail="", stderr_tail="")
            if command.startswith("git commit -m"):
                return repair.CommandResult(command=command, returncode=0, stdout_tail="committed", stderr_tail="")
            raise AssertionError(f"unexpected command: {command}")

        changed_calls = {"count": 0}

        def fake_changed(_repo_root: Path) -> list[str]:
            changed_calls["count"] += 1
            return ["scripts/weather/weather_image_forecast.py"] if changed_calls["count"] == 1 else []

        rev = subprocess.CompletedProcess(["git", "rev-parse", "HEAD"], 0, stdout="abc1234\n", stderr="")
        with (
            patch.object(repair, "run_command", side_effect=fake_run),
            patch.object(repair, "git_changed_files", side_effect=fake_changed),
            patch.object(repair.subprocess, "run", return_value=rev),
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
    assert result.commit == "abc1234"
    assert result.retry_allowed is True
    assert "git add -A" in calls
    assert any(command.startswith("git commit -m") for command in calls)


def test_verified_changed_run_fails_without_commit_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()

        def fake_run(command: str, repo_root: Path) -> repair.CommandResult:
            if command == "verify":
                return repair.CommandResult(command=command, returncode=0, stdout_tail="ok", stderr_tail="")
            if command == "git add -A":
                return repair.CommandResult(command=command, returncode=0, stdout_tail="", stderr_tail="")
            if command.startswith("git commit -m"):
                return repair.CommandResult(command=command, returncode=1, stdout_tail="", stderr_tail="nothing to commit")
            raise AssertionError(f"unexpected command: {command}")

        with (
            patch.object(repair, "run_command", side_effect=fake_run),
            patch.object(repair, "git_changed_files", return_value=["scripts/openclaw/x.py"]),
        ):
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
    assert "uncommitted changes remain" in result.evidence

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print(f"{Path(__file__).name}: ok")
