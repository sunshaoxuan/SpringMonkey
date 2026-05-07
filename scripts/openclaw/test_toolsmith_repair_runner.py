from __future__ import annotations

import tempfile
from unittest.mock import patch
from pathlib import Path

import toolsmith_repair_runner as runner


def test_toolsmith_generates_readonly_repair_package() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = runner.generate_repair_package(
            text="请查询公开天气信息",
            reason="no registered tool for weather lookup",
            safety_class="auto_safe_readonly",
            kernel_root=root / "kernel",
            repo_root=root / "repo",
        )
    assert package.status == "generated"
    assert package.write_operation is False
    assert package.permission_scope == "owner_dm_readonly"
    assert package.replay_policy == "verify_before_replay"
    assert package.registry_patch["tool_id"] == package.tool_id
    assert package.verify_command
    assert len(package.files) >= 3
    assert package.fingerprint


def test_toolsmith_blocks_write_repair_package() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = runner.generate_repair_package(
            text="请取消这单订车",
            reason="missing cancellation executor",
            safety_class="requires_confirmation_or_credentials",
            kernel_root=root / "kernel",
            repo_root=root / "repo",
            registry_tool={"tool_id": "timescar.dm.cancel_next", "entrypoint": "scripts/timescar/cancel.py", "write_operation": True},
        )
    assert package.status == "blocked_requires_authorization"
    assert package.write_operation is True
    assert package.replay_policy == "blocked_until_human_authorization"


def test_toolsmith_promotes_readonly_package_after_verify() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        (repo / "config" / "openclaw").mkdir(parents=True)
        (repo / "scripts" / "openclaw").mkdir(parents=True)
        (repo / "config" / "openclaw" / "intent_tools.json").write_text(
            '{"schema_version": 1, "tools": []}\n',
            encoding="utf-8",
        )
        package = runner.generate_repair_package(
            text="请查询公开天气信息",
            reason="no registered tool for weather lookup",
            safety_class="auto_safe_readonly",
            kernel_root=root / "kernel",
            repo_root=repo,
        )
        package.registry_patch["implementation_status"] = "ready"
        with patch("toolsmith_repair_runner.run_command", return_value=(True, "ok")):
            promoted = runner.verify_and_promote_package(package, kernel_root=root / "kernel", repo_root=repo)
        helper_exists = (repo / promoted.entrypoint).is_file()
        registry_text = (repo / "config" / "openclaw" / "intent_tools.json").read_text(encoding="utf-8")
        helper_registry_exists = (root / "kernel" / "helper_registry.json").is_file()

    assert promoted.status == "promoted"
    assert helper_exists
    assert promoted.tool_id in registry_text
    assert helper_registry_exists


def test_toolsmith_defers_promotion_without_formal_registry() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = runner.generate_repair_package(
            text="请查询公开天气信息",
            reason="no registered tool for weather lookup",
            safety_class="auto_safe_readonly",
            kernel_root=root / "kernel",
            repo_root=root / "repo",
        )
        promoted = runner.verify_and_promote_package(package, kernel_root=root / "kernel", repo_root=root / "repo")

    assert promoted.status == "generated"
    assert "candidate draft" in promoted.verify_output
