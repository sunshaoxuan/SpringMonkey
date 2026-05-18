#!/usr/bin/env python3
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import weather_image_forecast as mod

def fake_fetch_json(url: str) -> dict:
    if "air-quality" in url:
        return {"current": {"us_aqi": 36}}
    return {"current": {"temperature_2m": 22, "weather_code": 2, "precipitation": 0, "wind_speed_10m": 12, "uv_index": 4}, "daily": {"weather_code": [2], "temperature_2m_max": [27], "temperature_2m_min": [17], "precipitation_probability_max": [30]}}

def main() -> int:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    with tempfile.TemporaryDirectory(prefix="weather_image_forecast_") as tmp:
        cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)
        assert len(cards) == 2
        assert {card.area for card in cards} == {"杉並区", "川口市"}
        path = mod.write_weather_image(cards, now, Path(tmp))
        assert path.is_file()
        svg = path.read_text(encoding="utf-8")
        assert "天气预报 3D 微缩景观" in svg
        assert "杉並区" in svg and "川口市" in svg
        assert "Data source: Open-Meteo" in svg
        assert "brand marks" in svg
        reply = mod.build_media_reply(path, cards, now, day_kind)
        assert reply.startswith("MEDIA:")
        assert str(path) in reply
        assert "3D 微缩景观" in reply
        assert "Open-Meteo" in reply
    print("test_weather_image_forecast.py: ok")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
