from __future__ import annotations

import tempfile
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
