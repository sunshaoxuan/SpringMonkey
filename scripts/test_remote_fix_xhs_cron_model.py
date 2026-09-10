from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    path = Path(__file__).with_name("remote_fix_xhs_cron_model.py")
    spec = importlib.util.spec_from_file_location("remote_fix_xhs_cron_model", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_xhs_cron_model_fix_uses_official_cron_cli() -> None:
    module = load_module()
    remote = module.REMOTE

    assert module.TARGET_MODEL == "openai-codex/gpt-5.6-sol"
    assert module.SUBAGENT_POLICY_MARKER == "[xhs-current-run-only]"
    assert "cron/jobs.json" not in remote
    assert "cron\", \"list\", \"--json\"" in remote
    assert "openclaw --no-color cron edit" in remote
    assert "--model \"$TARGET_MODEL\"" in remote
    assert "--fallbacks \"\"" in remote
    assert "Do not call sessions_spawn" in remote
    assert "CURRENT_RUN_ONLY=" in remote
    assert "policy_marker not in message" in remote
