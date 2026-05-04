#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from unittest.mock import patch

import handle_dm_weather_query as mod

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def fake_fetch_json(_url: str, timeout: int = 30) -> dict:
    hours = [f"2026-05-05T{hour:02d}:00" for hour in range(24)]
    return {
        "hourly": {
            "time": hours,
            "temperature_2m": [12 + hour / 2 for hour in range(24)],
            "weather_code": [1] * 24,
            "precipitation_probability": [20] * 24,
            "wind_speed_10m": [18] * 24,
            "wind_gusts_10m": [28] * 24,
            "visibility": [12000] * 24,
        }
    }


def main() -> int:
    with patch.object(mod, "fetch_json", side_effect=fake_fetch_json):
        report = mod.build_report(
            "请查询明天东京和长野天气、风况和能见度",
            "2026-05-04T18:00:00+09:00",
        )
    assert "2026-05-05" in report
    assert "- 东京:" in report
    assert "- 长野:" in report
    assert "最大风速18km/h" in report
    assert "最低能见度12.0km" in report
    print(json.dumps({"ok": True, "report": report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
