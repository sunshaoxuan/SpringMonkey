#!/usr/bin/env python3
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import subprocess

import weather_image_forecast as mod

def fake_fetch_json(url: str) -> dict:
    if "air-quality" in url:
        return {"current": {"us_aqi": 36}}
    return {"current": {"temperature_2m": 22, "weather_code": 2, "precipitation": 0, "wind_speed_10m": 12, "uv_index": 4}, "daily": {"weather_code": [2], "temperature_2m_max": [27], "temperature_2m_min": [17], "precipitation_probability_max": [30]}}

def main() -> int:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    with tempfile.TemporaryDirectory(prefix="weather_image_forecast_") as tmp:
        cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)
        assert len(cards) == 1
        assert cards[0].city == "東京"
        assert cards[0].area == "杉並区、川口市、品川区"
        path = mod.write_weather_image(cards, now, Path(tmp))
        assert path.is_file()
        assert path.suffix == ".png"
        assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        reply = mod.build_media_reply(path, cards, now, day_kind)
        assert reply == f"MEDIA:{path}"
    print("test_weather_image_forecast.py: ok")
    return 0


def test_model_image_generation_is_preferred(tmp_path: Path) -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)
    expected = tmp_path / "model.png"
    try:
        from PIL import Image
        Image.new("RGB", (1024, 1536), (240, 244, 250)).save(expected)
    except Exception:
        expected.write_bytes(mod.render_png(cards, now))
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"outputs": [{"path": str(expected)}]}), stderr="")

    path = mod.write_weather_image_with_model(cards, now, tmp_path, day_kind=day_kind, command_runner=fake_run)

    assert path == expected
    assert calls
    assert calls[0][:5] == ["openclaw", "infer", "image", "generate", "--model"]
    assert "openai/gpt-image-2" in calls[0]
    assert "1024x1365" in calls[0]


def test_same_city_locations_merge_before_image_generation() -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, _day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)

    assert len(cards) == 1
    assert cards[0].label == "東京"
    assert cards[0].city == "東京"
    assert "杉並区" in cards[0].area
    assert "川口市" in cards[0].area
    assert "品川区" in cards[0].area


def test_prompt_matches_vertical_single_city_image_contract() -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)
    prompt = mod.build_image_prompt(cards, now, day_kind)

    assert "vertical 3:4" in prompt
    assert "one city scene" in prompt
    assert "45-degree top-down isometric" in prompt
    assert "cute 3D chibi miniature city landmark diorama" in prompt
    assert "PBR materials" in prompt
    assert "minimal pure-color soft background" in prompt
    assert "no panels, no cards, no text boxes" in prompt
    assert "large city name" in prompt
    assert "date in very small type" in prompt
    assert "temperature range in medium type" in prompt
    assert "東京" in prompt


def test_model_output_is_normalized_to_three_by_four(tmp_path: Path) -> None:
    try:
        from PIL import Image
    except Exception:
        return
    path = tmp_path / "model.png"
    Image.new("RGB", (1024, 1536), (240, 244, 250)).save(path)

    mod.normalize_png_aspect(path)

    with Image.open(path) as image:
        assert image.size == (1024, 1365)


def test_model_image_generation_falls_back_to_deterministic_png(tmp_path: Path) -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="image model unavailable")

    path = mod.write_weather_image_with_model(cards, now, tmp_path, day_kind=day_kind, command_runner=fake_run)

    assert path.suffix == ".png"
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

if __name__ == "__main__":
    raise SystemExit(main())
