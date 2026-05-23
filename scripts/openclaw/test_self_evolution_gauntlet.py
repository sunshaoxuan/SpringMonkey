from __future__ import annotations

from pathlib import Path

import self_evolution_gauntlet as gauntlet
import verify_self_evolution_closure as closure


def test_readonly_gauntlet_creates_real_commit(tmp_path: Path) -> None:
    result = gauntlet.run_gauntlet(
        scenario="readonly-helper-regression",
        repo_root=gauntlet.REPO,
        kernel_root=tmp_path / "kernel",
        state_path=tmp_path / "tasks.json",
    )

    assert result.ok is True
    assert result.status == "final_succeeded"
    assert result.commit
    assert result.changed_files
    assert result.replay_allowed is True


def test_write_gauntlet_keeps_external_replay_gated(tmp_path: Path) -> None:
    result = gauntlet.run_gauntlet(
        scenario="write-tool-regression",
        repo_root=gauntlet.REPO,
        kernel_root=tmp_path / "kernel",
        state_path=tmp_path / "tasks.json",
    )

    assert result.ok is True
    assert result.status == "final_succeeded"
    assert result.commit
    assert result.replay_allowed is False
    assert "gated" in result.replay_reason


def test_closure_requires_gauntlet_records(tmp_path: Path) -> None:
    root = tmp_path / "kernel"
    gauntlet.run_gauntlet(
        scenario="readonly-helper-regression",
        repo_root=gauntlet.REPO,
        kernel_root=root,
        state_path=tmp_path / "tasks.json",
    )
    gauntlet.run_gauntlet(
        scenario="write-tool-regression",
        repo_root=gauntlet.REPO,
        kernel_root=root,
        state_path=tmp_path / "tasks.json",
    )

    checks = closure.check_gauntlet(root)
    assert all(item.ok for item in checks)
