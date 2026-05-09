#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


def load_installer_module():
    path = Path(__file__).with_name("remote_install_discord_gateway_watchdog.py")
    spec = importlib.util.spec_from_file_location("remote_install_discord_gateway_watchdog", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_watchdog_detects_discord_start_account_stall() -> None:
    module = load_installer_module()
    remote = module.REMOTE

    assert "STARTUP_STUCK_PHASE = \"phase=channels.discord.start-account\"" in remote
    assert "STARTUP_STUCK_HINT = \"client initialized as\"" in remote
    assert "discord_startup_stalled" in remote
    assert "no_recent_discord_gateway_timeout_or_startup_stall" in remote


if __name__ == "__main__":
    test_watchdog_detects_discord_start_account_stall()
    print("OK")
