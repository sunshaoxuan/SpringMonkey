from __future__ import annotations

import json
import tempfile
from pathlib import Path

import domain_implementation_runner as runner


def test_default_model_uses_codex_gpt_5_6_provider() -> None:
    assert runner.DEFAULT_MODEL == "openai-codex/gpt-5.6"


def write_package(root: Path) -> Path:
    package_dir = root / "kernel" / "toolsmith_packages" / "repair_demo"
    package_dir.mkdir(parents=True)
    state = {
        "package_id": "repair_demo",
        "status": "planned",
        "gap_type": "permission_missing",
        "safety_class": "auto_safe_readonly",
        "tool_id": "openclaw.repair_plan.demo",
        "entrypoint": "",
        "permission_scope": "requires_authorization",
        "write_operation": True,
        "verify_command": "",
        "replay_policy": "blocked_until_domain_implementation",
        "package_dir": str(package_dir),
        "registry_patch": {},
        "files": [],
        "reason": "known direction needs implementation",
        "created_at": "2026-05-16T00:00:00+00:00",
        "fingerprint": "abc123",
    }
    path = package_dir / "package_state.json"
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return path


def test_start_implementation_dry_run_registers_long_task_idempotently() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state_path = root / "long_tasks.json"
        run_dir = root / "runs"
        package_state = write_package(root)
        first = runner.start_implementation(
            package_state=package_state,
            text="请补齐一个已知方向能力",
            reason="binding gap",
            repo_root=root,
            kernel_root=root / "kernel",
            state_path=state_path,
            run_dir=run_dir,
            dry_run=True,
        )
        second = runner.start_implementation(
            package_state=package_state,
            text="请补齐一个已知方向能力",
            reason="binding gap",
            repo_root=root,
            kernel_root=root / "kernel",
            state_path=state_path,
            run_dir=run_dir,
            dry_run=True,
        )
        prompt_text = Path(first.prompt_file).read_text(encoding="utf-8")

        assert first.status == "running"
        assert first.evidence == "dry_run_registered"
        assert first.run_id == second.run_id
        assert second.evidence == "existing_run_reused"
        assert Path(first.prompt_file).is_file()
        assert "不要把具体用户任务硬编码成路由规则" in prompt_text


def test_implementation_subprocess_env_forces_service_config_and_key_aliases(monkeypatch, tmp_path: Path) -> None:
    secret = tmp_path / "codex.key"
    secret.write_text("secret-value\n", encoding="utf-8")
    env_file = tmp_path / "openclaw.env"
    env_file.write_text(
        "\n".join(
            [
                "OPENCLAW_PUBLIC_MODEL_BASE_URL=http://ccnode.briconbric.com:49530/v1",
                f"NEWS_CODEX_API_KEY_FILE={secret}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "RUNTIME_ENV_FILES", (env_file,))

    env = runner.implementation_subprocess_env(
        {
            "OPENCLAW_CONFIG_PATH": "/tmp/wrong-openclaw.json",
            "OPENCLAW_STATE_DIR": "/tmp/wrong-state",
            "PYTHONIOENCODING": "cp932",
        }
    )

    assert env["OPENCLAW_CONFIG_PATH"] == str(runner.SERVICE_CONFIG_PATH)
    assert env["OPENCLAW_STATE_DIR"] == str(runner.SERVICE_STATE_DIR)
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["NEWS_CODEX_API_KEY"] == "secret-value"
    assert env["OPENCLAW_PUBLIC_MODEL_API_KEY"] == "secret-value"
    assert env["OPENCLAW_CODEX_API_KEY"] == "secret-value"
