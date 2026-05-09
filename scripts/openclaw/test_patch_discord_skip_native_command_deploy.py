from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    path = Path(__file__).with_name("patch_discord_skip_native_command_deploy.py")
    spec = importlib.util.spec_from_file_location("patch_discord_skip_native_command_deploy", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_patch_replaces_background_deploy(tmp_path: Path) -> None:
    module = load_module()
    provider = tmp_path / "provider-hTInySyN.js"
    provider.write_text("before\n" + module.OLD + "\nafter\n", encoding="utf-8")

    changed = module.patch_file(provider)

    text = provider.read_text(encoding="utf-8")
    assert changed is True
    assert module.OLD not in text
    assert "deploy-commands:skipped" in text
    assert "springmonkey_dm_first_startup_guard" in text
