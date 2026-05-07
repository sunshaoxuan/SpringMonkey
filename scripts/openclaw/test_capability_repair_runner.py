from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import capability_repair_runner as runner


def test_repair_runner_logs_verified_readonly_replay_event() -> None:
    tool = {
        "tool_id": "weather.dm.query",
        "entrypoint": "scripts/weather/handle_dm_weather_query.py",
        "write_operation": False,
        "verify_command": "python -m compileall -q scripts/weather/handle_dm_weather_query.py",
    }
    with tempfile.TemporaryDirectory() as tmp, patch("dm_capability_gap_runner.run_verify_command", return_value=(True, "ok")):
        root = Path(tmp) / "kernel"
        result = runner.run_repair(
            text="请查询明天东京天气和风况",
            channel="discord_dm",
            user_id="tester",
            stage="execute",
            reason="registered tool returned non-zero exit code 1",
            kernel_root=root,
            repo_root=Path(tmp),
            registry_tool=tool,
        )
        assert result.status == "verified"
        assert result.replay_allowed is True
        event_log = Path(result.event_log)
        events = [json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines()]
    assert events[-1]["stage"] == "execute"
    assert events[-1]["runner_status"] == "verified"
    assert events[-1]["replay_allowed"] is True


def test_repair_runner_blocks_write_replay() -> None:
    tool = {
        "tool_id": "timescar.dm.cancel_next",
        "entrypoint": "scripts/timescar/timescar_cancel_reservation.py",
        "write_operation": True,
    }
    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_repair(
            text="请取消这单订车",
            channel="discord_dm",
            user_id="tester",
            stage="execute",
            reason="registered tool missing verified submitter",
            kernel_root=Path(tmp) / "kernel",
            repo_root=Path(tmp),
            registry_tool=tool,
        )
    assert result.status == "blocked"
    assert result.replay_allowed is False
    assert "not a verified read-only tool" in result.replay_reason or result.safety_class == "requires_confirmation_or_credentials"


def test_repair_runner_records_toolsmith_package_for_unverified_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_repair(
            text="请帮我做一个新的只读查询",
            channel="discord_dm",
            user_id="tester",
            stage="binding",
            reason="no registered tool for readonly lookup",
            kernel_root=Path(tmp) / "kernel",
            repo_root=Path(tmp),
            forced_safety_class="auto_safe_readonly",
            forced_safety_reason="test readonly gap",
        )
        events = [json.loads(line) for line in Path(result.event_log).read_text(encoding="utf-8").splitlines()]
    assert result.status in {"generated", "verified"}
    assert events[-1]["resolved_by"]
    assert events[-1]["resolved_by"]["replay_policy"] in {"verify_before_replay", "blocked_until_human_authorization"}
