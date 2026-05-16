from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import dm_capability_gap_runner as runner


def test_unclassified_gap_does_not_promote_by_business_keywords() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_gap(
            text="请查询明天东京和长野天气、风况和能见度",
            channel="discord_dm",
            user_id="999",
            intent_reason="weather lookup",
            kernel_root=Path(tmp) / "kernel",
            repo_root=Path(tmp),
        )
    assert result.status == "blocked"
    assert result.safety_class == "unsupported_or_ambiguous"
    assert result.registry_tool is None
    assert result.plan.status == "blocked_requires_human_or_registered_tool"


def test_forced_readonly_gap_can_promote_explicit_registry_tool() -> None:
    registry_tool = {
        "tool_id": "weather.dm.query",
        "entrypoint": "scripts/weather/handle_dm_weather_query.py",
        "verify_command": "python -m compileall -q scripts/weather/handle_dm_weather_query.py",
        "write_operation": False,
    }
    with tempfile.TemporaryDirectory() as tmp:
        with patch.object(runner, "run_verify_command", return_value=(True, "ok")):
            result = runner.run_gap(
                text="请查询明天东京和长野天气、风况和能见度",
                channel="discord_dm",
                user_id="999",
                intent_reason="semantic classifier selected weather query",
                kernel_root=Path(tmp) / "kernel",
                repo_root=Path(tmp),
                forced_safety_class="auto_safe_readonly",
                forced_safety_reason="model selected safe read-only capability",
                registry_tool=registry_tool,
            )
    assert result.status == "promoted"
    assert result.safety_class == "auto_safe_readonly"
    assert result.registry_tool == registry_tool
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
    assert result.safety_class == "unsupported_or_ambiguous"
    assert result.registry_tool is None
    assert "不能自动执行" in result.reply


def test_timescar_cancel_gap_does_not_generate_tool_plan_from_keywords() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_gap(
            text="请取消这单订车",
            channel="discord_dm",
            user_id="999",
            intent_reason="registered tool reported missing verified cancel submitter",
            kernel_root=Path(tmp) / "kernel",
            repo_root=Path(tmp),
    )
    assert result.status == "blocked"
    assert result.safety_class == "unsupported_or_ambiguous"
    assert result.registry_tool is None
    assert result.plan.entrypoint is None
