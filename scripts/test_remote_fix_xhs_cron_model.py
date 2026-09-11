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
    assert module.OWNER_ACCESS_POLICY_MARKER == "[xhs-owner-access]"
    assert "cron/jobs.json" not in remote
    assert "cron\", \"list\", \"--json\"" in remote
    assert "openclaw --no-color cron edit" in remote
    assert "--model \"$TARGET_MODEL\"" in remote
    assert "--fallbacks \"\"" in remote
    assert "Do not call sessions_spawn" in remote
    assert "at most 8 product or image source page fetches" in remote
    assert "at most 12 browser snapshots" in remote
    assert "never copy full-page HTML or full-page text" in remote
    assert "stop researching and write the Google Doc immediately" in remote
    assert "OPENCLAW_OWNER_GOOGLE_EMAIL is required" in remote
    assert "share the Google Doc directly with {owner_email} as Viewer" in remote
    assert "Do not create an anyone-with-link permission" in remote
    assert "artifact_registry.py record" in remote
    assert "same helper's latest command" in remote
    assert "OWNER_ACCESS_POLICY=" in remote
    assert "CURRENT_RUN_ONLY=" in remote
    assert "policy_marker not in message" in remote
