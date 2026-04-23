#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import discord_weather_report as mod


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="weather_trace_") as tmp:
        mod.STATE_DIR = Path(tmp) / "state"
        import staged_jobs.task_trace as trace_mod

        trace_mod.TRACE_ROOT = Path(tmp) / "traces"
        original_fetch_json = mod.fetch_json
        try:
            def fake_fetch_json(url: str) -> dict:
                if "forecast" in url:
                    return {
                        "current": {
                            "temperature_2m": 21,
                            "weather_code": 1,
                            "precipitation": 0,
                            "wind_speed_10m": 10,
                            "uv_index": 3,
                        },
                        "daily": {
                            "temperature_2m_max": [26],
                            "temperature_2m_min": [16],
                            "precipitation_probability_max": [20],
                        },
                    }
                return {"current": {"us_aqi": 42}}
            mod.fetch_json = fake_fetch_json
            result = mod.fetch_weather(mod.Location("测试地点", "测试区", 35.0, 139.0))
        finally:
            mod.fetch_json = original_fetch_json
        assert "测试地点" in result
        print(json.dumps({"line": result}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
