#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


def load_installer_module():
    path = Path(__file__).with_name("remote_install_direct_discord_cron.py")
    spec = importlib.util.spec_from_file_location("remote_install_direct_discord_cron", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_news_cron_preserves_command_substitution_for_helper() -> None:
    module = load_installer_module()
    remote = module.REMOTE
    news_lines = [line for line in remote.splitlines() if "--name news-digest-jst-" in line]

    assert 'cat >"${CRON_FILE}" <<\'EOF\'' in remote
    assert len(news_lines) == 2
    for line in news_lines:
        assert "--command bash -lc 'set -e; OUT=$(python3 /var/lib/openclaw/repos/SpringMonkey/" in line
        assert 'DIR=$(printf "%s\\n" "$OUT"' in line
        assert 'cat "$DIR/final_broadcast.md"\'' in line
        assert r"OUT=\$(python3" not in line
        assert "${REPO}" not in line


if __name__ == "__main__":
    test_news_cron_preserves_command_substitution_for_helper()
    print("OK")
