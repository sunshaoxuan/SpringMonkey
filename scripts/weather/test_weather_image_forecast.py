#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import os
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
        assert len(cards) == 3
        assert [card.city for card in cards] == ["東京", "北京", "大连"]
        assert [card.area for card in cards] == ["東京", "北京", "大连"]
        paths = mod.write_weather_images(cards, now, Path(tmp))
        assert len(paths) == 3
        for path in paths:
            assert path.is_file()
            assert path.suffix == ".png"
            data = path.read_bytes()
            assert data.startswith(b"\x89PNG\r\n\x1a\n")
            import struct

            assert struct.unpack(">II", data[16:24]) == (1024, 1024)
        reply = mod.build_media_reply(paths, cards, now, day_kind)
        assert reply == "\n".join(f"MEDIA:{path}" for path in paths)
    print("test_weather_image_forecast.py: ok")
    return 0


def test_model_image_generation_is_preferred(tmp_path: Path) -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)
    expected = tmp_path / "model.png"
    expected.write_bytes(mod._png_bytes(1024, 1024, bytearray(os.urandom(1024 * 1024 * 3))))
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"outputs": [{"path": str(expected)}]}), stderr="")

    path = mod.write_weather_image_with_model([cards[0]], now, tmp_path, day_kind=day_kind, command_runner=fake_run)

    assert path == expected
    assert calls
    assert calls[0][:5] == ["openclaw", "infer", "image", "generate", "--model"]
    assert "openai/gpt-image-2" in calls[0]
    assert "1024x1024" in calls[0]


def test_weather_image_locations_are_three_city_forecast_spec() -> None:
    assert [(loc.label, loc.area) for loc in mod.WEATHER_IMAGE_LOCATIONS] == [
        ("東京", "東京"),
        ("北京", "北京"),
        ("大连", "大连"),
    ]


def test_same_city_locations_merge_before_image_generation() -> None:
    cards = [
        mod.WeatherCard("a", "杉並区", "東京", "tokyo tower", 20, 1, 10, 5, 2, 30, 25, 15, "ok"),
        mod.WeatherCard("b", "品川区", "東京", "skytree", 22, 61, 50, 7, 3, 40, 28, 17, "rain"),
    ]

    merged = mod.merge_same_city_cards(cards)

    assert len(merged) == 1
    assert merged[0].label == "東京"
    assert merged[0].city == "東京"
    assert "杉並区" in merged[0].area
    assert "品川区" in merged[0].area


def test_prompt_matches_square_single_city_image_contract() -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)
    prompt = mod.build_image_prompt([cards[0]], now, day_kind)

    assert "square 1:1 1024x1024" in prompt
    assert "one city scene" in prompt
    assert "45-degree top-down isometric" in prompt
    assert "cute 3D chibi miniature city landmark diorama" in prompt
    assert "choose exactly one recognizable landmark per city" in prompt
    assert "classic Japanese children's cartoon warmth" in prompt
    assert "without any copyrighted characters" in prompt
    assert "PBR materials" in prompt
    assert "minimal pure-color soft background" in prompt
    assert "no panels, no cards, no text boxes" in prompt
    assert "large city name" in prompt
    assert "date in very small type" in prompt
    assert "temperature range in medium type" in prompt
    assert "東京" in prompt


def test_model_output_is_normalized_to_square(tmp_path: Path) -> None:
    try:
        from PIL import Image
    except Exception:
        return
    path = tmp_path / "model.png"
    Image.new("RGB", (1024, 1536), (240, 244, 250)).save(path)

    mod.normalize_png_aspect(path)

    with Image.open(path) as image:
        assert image.size == (1024, 1024)


def test_stdlib_png_normalizer_crops_truecolor_png(tmp_path: Path) -> None:
    path = tmp_path / "stdlib.png"
    pixels = bytearray([240, 244, 250] * (1024 * 1536))
    path.write_bytes(mod._png_bytes(1024, 1536, pixels))

    mod._normalize_png_aspect_stdlib(path, target_width=1024, target_height=1024)

    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    import struct

    assert struct.unpack(">II", data[16:24]) == (1024, 1024)


def test_model_image_generation_falls_back_to_deterministic_png(tmp_path: Path) -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="image model unavailable")

    try:
        mod.write_weather_image_with_model([cards[0]], now, tmp_path, day_kind=day_kind, command_runner=fake_run)
    except RuntimeError as exc:
        assert "image model unavailable" in str(exc)
    else:
        raise AssertionError("model generation failure must not silently fall back")


def test_deterministic_fallback_requires_explicit_model_mode(tmp_path: Path) -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)

    path = mod.write_weather_image_with_model([cards[0]], now, tmp_path, day_kind=day_kind, model="fallback")

    assert path.suffix == ".png"
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_batch_model_generation_refuses_partial_delivery(tmp_path: Path) -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)
    generated = tmp_path / "ok.png"
    generated.write_bytes(mod.render_png([cards[0]], now) + b"0" * mod.MIN_MODEL_IMAGE_BYTES)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"outputs": [{"path": str(generated)}]}), stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="model timeout")

    try:
        mod.write_weather_images_with_model(cards, now, tmp_path, day_kind=day_kind, command_runner=fake_run)
    except RuntimeError as exc:
        assert "refusing partial delivery" in str(exc)
        assert "北京" in str(exc)
        assert "大连" in str(exc)
    else:
        raise AssertionError("partial weather image generation must fail")


def test_build_media_reply_rejects_suspicious_model_placeholder(tmp_path: Path) -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)
    placeholder = tmp_path / "weather_miniature_大连_20260519_070000_image2.png"
    placeholder.write_bytes(mod.render_png([cards[0]], now))

    try:
        mod.build_media_reply([placeholder], [cards[0]], now, day_kind)
    except RuntimeError as exc:
        assert "suspiciously small" in str(exc)
    else:
        raise AssertionError("small model image placeholders must not be delivered")

if __name__ == "__main__":
    raise SystemExit(main())
