from __future__ import annotations

import importlib.util
from pathlib import Path


def load_installer_module():
    path = Path(__file__).with_name("remote_install_sub2api_qwen_fallback.py")
    spec = importlib.util.spec_from_file_location("remote_install_sub2api_qwen_fallback", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_qwen_fallback_installer_is_exact_model_and_smoke_gated() -> None:
    module = load_installer_module()
    remote = module.REMOTE

    assert module.MODEL == "hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S"
    assert module.BASE_URL == "http://ccnode.briconbric.com:49530/v1"
    assert module.INTENT_TIMEOUT_SECONDS == 180
    assert 'base_url + "/models"' in remote
    assert 'base_url + "/chat/completions"' in remote
    assert "QWEN_FALLBACK_SMOKE_OK" in remote
    assert "QWEN_FALLBACK_NOT_ENABLED" in remote
    assert "QWEN_FALLBACK_KEY_FILE_READY" in remote
    assert "invalid_intent_frame" in remote


def test_qwen_fallback_installer_writes_and_verifies_all_fallback_layers() -> None:
    remote = load_installer_module().REMOTE

    assert '"OPENCLAW_MODEL_FALLBACK": model' in remote
    assert '"OPENCLAW_MODEL_FALLBACK_TIMEOUT_SECONDS": timeout_seconds' in remote
    assert '"OPENCLAW_INTENT_FALLBACK_MODELS": model' in remote
    assert '"OPENCLAW_INTENT_FALLBACK_TIMEOUT_SECONDS": timeout_seconds' in remote
    assert "source \"$ENV_FILE\"" not in remote
    assert "os.replace(temporary, path)" in remote
    assert "/usr/local/lib/openclaw/ensure_model_auth_profiles.sh" in remote
    assert 'fallbacks != [expected_model]' in remote
    assert "if not path.is_file():" in remote
    assert "QWEN_FALLBACK_CONFIG_OK" in remote
