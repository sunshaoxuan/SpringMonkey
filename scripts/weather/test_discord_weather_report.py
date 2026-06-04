#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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
            text_report = mod.build_text_report(datetime(2026, 5, 7, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo")))
        finally:
            mod.fetch_json = original_fetch_json
        assert "测试地点" in result
        assert "天气预报 2026-05-07" in text_report

        original_load_holidays = mod.load_holidays
        try:
            mod.load_holidays = lambda target_year=None: {"2026-05-06": "憲法記念日 振替休日"}
            holiday_locations, holiday_rest_day, holiday_kind = mod.locations_for_day(
                datetime(2026, 5, 6, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
            )
            assert holiday_rest_day is True
            assert "祝日" in holiday_kind
            assert [loc.label for loc in holiday_locations] == ["原人自宅", "熊自宅"]

            weekday_locations, weekday_rest_day, weekday_kind = mod.locations_for_day(
                datetime(2026, 5, 7, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
            )
            assert weekday_rest_day is False
            assert weekday_kind == "平日"
            assert [loc.label for loc in weekday_locations] == ["原人自宅", "熊自宅", "会社"]
        finally:
            mod.load_holidays = original_load_holidays

    print(json.dumps({"line": result, "holiday_locations": [loc.label for loc in holiday_locations]}, ensure_ascii=True))
    return 0


def test_fetch_weather_payload_falls_back_to_wttr_on_open_meteo_failure(monkeypatch) -> None:
    location = mod.Location("东京", "東京", 35.6762, 139.6503)

    def fake_fetch_json(url: str, attempts: int = 3) -> dict:
        if "api.open-meteo.com" in url:
            raise RuntimeError("open-meteo down")
        if "wttr.in" in url:
            return {
                "current_condition": [{"temp_C": "21", "weatherCode": "113", "precipMM": "0.0", "windspeedKmph": "12"}],
                "weather": [
                    {
                        "maxtempC": "24",
                        "mintempC": "18",
                        "hourly": [
                            {"time": "2026-05-19 00", "tempC": "18", "weatherCode": "113", "chanceofrain": "0", "windspeedKmph": "12"},
                        ],
                    }
                ],
            }
        raise AssertionError(url)

    payload = mod.fetch_weather_payload(location, fetch_json=fake_fetch_json)

    assert payload["source"] == "wttr"
    assert payload["current"]["temperature_2m"] == 21.0
    assert payload["daily"]["temperature_2m_max"][0] == 24.0


def test_weather_payload_reports_all_providers_failure(monkeypatch) -> None:
    location = mod.Location("东京", "東京", 35.6762, 139.6503)

    def fake_fetch_json(_url: str) -> dict:
        raise RuntimeError("service unavailable")

    try:
        mod.fetch_weather_payload(location, fetch_json=fake_fetch_json)
    except Exception as exc:
        message = str(exc)
        assert "weather services all failed" in message
        assert "open-meteo" in message
        assert "wttr" in message
    else:
        raise AssertionError("expecting weather payload fetch failure")


if __name__ == "__main__":
    raise SystemExit(main())
