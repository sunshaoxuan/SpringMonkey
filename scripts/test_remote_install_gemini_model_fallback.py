from __future__ import annotations

import importlib.util
from pathlib import Path


def load_installer_module():
    path = Path(__file__).with_name("remote_install_gemini_model_fallback.py")
    spec = importlib.util.spec_from_file_location("remote_install_gemini_model_fallback", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gemini_fallback_installer_is_smoke_gated() -> None:
    module = load_installer_module()
    remote = module.REMOTE

    assert "GEMINI_FALLBACK_SMOKE_OK" in remote
    assert "GEMINI_FALLBACK_NOT_ENABLED" in remote
    assert "/chat/completions" in remote
    assert "Reply with exactly: ok" in remote


def test_gemini_fallback_installer_uses_49530_and_not_22545() -> None:
    module = load_installer_module()

    assert module.BASE_URL == "http://ccnode.briconbric.com:49530/v1"
    assert module.MODEL == "gemini-pro-agent"
    assert "22545" not in module.REMOTE


def test_gemini_fallback_installer_writes_explicit_fallback_vars() -> None:
    module = load_installer_module()
    remote = module.REMOTE

    assert "OPENCLAW_MODEL_FALLBACK_PROVIDER" in remote
    assert "OPENCLAW_MODEL_FALLBACK_BASE_URL" in remote
    assert "OPENCLAW_MODEL_FALLBACK_API_KEY_FILE" in remote
    assert "OPENCLAW_INTENT_FALLBACK_BASE_URL" in remote
    assert "OPENCLAW_INTENT_FALLBACK_API_KEY_FILE" in remote
    assert "NEWS_FALLBACK_MODEL" in remote
    assert 'defaults.setdefault("model", {})["fallbacks"] = [f"openai-codex/{model}"]' in remote
