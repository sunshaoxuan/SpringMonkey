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

    assert "python3 scripts/news/apply_news_config.py" in remote
    assert 'cat >"${CRON_FILE}" <<\'EOF\'' in remote
    assert len(news_lines) == 2
    for line in news_lines:
        assert "--command bash -lc 'set -e; OUT=$(python3 /var/lib/openclaw/repos/SpringMonkey/" in line
        assert "--timeout 7200" in line
        assert 'DIR=$(echo "$OUT" | sed -n "s/^PIPELINE_OK //p"' in line
        assert "printf" not in line
        assert "%" not in line
        assert 'cat "$DIR/final_broadcast.md"\'' in line
        assert r"OUT=\$(python3" not in line
        assert "${REPO}" not in line


def test_weather_cron_uses_image_forecast_with_long_timeout() -> None:
    module = load_installer_module()
    remote = module.REMOTE
    weather_lines = [line for line in remote.splitlines() if "--name weather-report-jst-0700 " in line]

    assert weather_lines
    for line in weather_lines:
        assert "--timeout 1800" in line
        assert "OPENCLAW_WEATHER_IMAGE_MODEL_CANDIDATES=openai/gpt-image-2" in line
        assert "OPENCLAW_WEATHER_DATA_PROVIDERS=open-meteo,wttr" in line
        assert "OPENCLAW_WEATHER_ALLOW_DETERMINISTIC_FALLBACK=1" not in line
        assert "scripts/weather/weather_image_forecast.py" in line
        assert "scripts/weather/discord_weather_report.py" not in line


def test_weather_public_delivery_requires_model_media_quality_gate() -> None:
    module = load_installer_module()
    remote = module.REMOTE

    assert "def should_deliver_public" in remote
    assert 'path.name.endswith("_image2.png")' in remote
    assert "path.stat().st_size >= 100000" in remote
    assert "天气预报没有生成完整的高质量模型图片" in remote


def test_direct_cron_failure_records_repair_gap() -> None:
    module = load_installer_module()
    remote = module.REMOTE

    assert "def record_direct_failure_gap" in remote
    assert "agent_society_runtime_record_gap.py" in remote
    assert "direct-cron:{name}" in remote
    assert "repairGap" in remote
    assert "--record-only" in remote
    assert "classify direct cron failure" in remote


def test_run_as_openclaw_preserves_openclaw_home_for_oauth() -> None:
    module = load_installer_module()
    remote = module.REMOTE

    assert '["runuser", "-u", "openclaw", "--", "env", "HOME=/var/lib/openclaw", *command]' in remote


if __name__ == "__main__":
    test_news_cron_preserves_command_substitution_for_helper()
    test_weather_cron_uses_image_forecast_with_long_timeout()
    test_direct_cron_failure_records_repair_gap()
    test_run_as_openclaw_preserves_openclaw_home_for_oauth()
    print("OK")
