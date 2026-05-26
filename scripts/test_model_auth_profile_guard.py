#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


def load_installer_module():
    path = Path(__file__).with_name("remote_install_model_auth_profile_guard.py")
    spec = importlib.util.spec_from_file_location("remote_install_model_auth_profile_guard", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_auth_guard_does_not_periodically_rewrite_runtime_config() -> None:
    module = load_installer_module()
    remote = module.REMOTE

    assert "OnUnitActiveSec=60" not in remote
    assert "systemctl enable --now openclaw-model-auth-profile-guard.timer" not in remote
    assert "systemctl disable --now openclaw-model-auth-profile-guard.timer" in remote


def test_model_auth_guard_does_not_hijack_openai_image_provider() -> None:
    module = load_installer_module()
    remote = module.REMOTE

    assert 'openai["baseUrl"] = "http://ccnode.briconbric.com:49530/v1"' not in remote
    assert 'openai["apiKey"] = secret' not in remote
    assert 'openai.pop("baseUrl", None)' in remote
    assert 'openai.pop("apiKey", None)' in remote
    assert 'defaults["primary"] = "openai-codex/gpt-5.5"' in remote
    assert 'last_good["openai"] = "openai:ccnode-codex"' not in remote


def test_model_auth_guard_keeps_openclaw_home_readable_by_openclaw_user() -> None:
    module = load_installer_module()
    remote = module.REMOTE

    assert 'pwd.getpwnam("openclaw")' in remote
    assert "os.chown(path, user.pw_uid, user.pw_gid)" in remote


if __name__ == "__main__":
    test_model_auth_guard_does_not_periodically_rewrite_runtime_config()
    test_model_auth_guard_does_not_hijack_openai_image_provider()
    print("OK")
