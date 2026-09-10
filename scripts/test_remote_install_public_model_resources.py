from __future__ import annotations

import importlib.util
from pathlib import Path


def load_installer_module():
    path = Path(__file__).with_name("remote_install_public_model_resources.py")
    spec = importlib.util.spec_from_file_location("remote_install_public_model_resources", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_model_resources_only_retires_ollama_fallback() -> None:
    remote = load_installer_module().REMOTE

    assert 'retired_generic_fallback = (' in remote
    assert 'retired_intent_fallback = "22545" in values.get("OPENCLAW_INTENT_FALLBACK_BASE_URL", "").lower()' in remote
    assert 'values.get("OPENCLAW_MODEL_FALLBACK_PROVIDER", "").lower() == "ollama"' in remote
    assert '"22545" in values.get("OPENCLAW_MODEL_FALLBACK_BASE_URL", "").lower()' in remote
    assert 'or "qwen" in lowered' not in remote
    assert 'alias.startswith("OPENCLAW_MODEL_FALLBACK")' in remote
    assert 'alias.startswith("OPENCLAW_INTENT_FALLBACK")' in remote
