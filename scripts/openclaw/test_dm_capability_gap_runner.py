from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import dm_capability_gap_runner as runner


def test_safe_readonly_weather_gap_promotes_registry_tool() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with patch.object(runner, "run_verify_command", return_value=(True, "ok")):
            result = runner.run_gap(
                text="请查询明天东京和长野天气、风况和能见度",
                channel="discord_dm",
                user_id="999",
                intent_reason="weather lookup",
                kernel_root=Path(tmp) / "kernel",
                repo_root=Path(tmp),
            )
    assert result.status == "promoted"
    assert result.safety_class == "auto_safe_readonly"
    assert result.registry_tool
    assert result.registry_tool["tool_id"] == "weather.dm.query"
    assert result.plan.status == "promoted_replay_ready"


def test_write_gap_records_plan_without_promoting_tool() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_gap(
            text="请帮我修改配置并重启服务",
            channel="discord_dm",
            user_id="999",
            intent_reason="write operation",
            kernel_root=Path(tmp) / "kernel",
            repo_root=Path(tmp),
        )
    assert result.status == "blocked"
    assert result.safety_class == "requires_confirmation_or_credentials"
    assert result.registry_tool is None
    assert "不能自动执行" in result.reply
