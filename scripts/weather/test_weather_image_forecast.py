#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import os
import base64
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

            assert struct.unpack(">II", data[16:24]) == (1024, 1536)
        reply = mod.build_media_reply(paths, cards, now, day_kind)
        assert reply == "\n".join(f"MEDIA:{path}" for path in paths)
    print("test_weather_image_forecast.py: ok")
    return 0


def test_model_image_generation_is_preferred(tmp_path: Path) -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)
    expected = tmp_path / "model.png"
    expected.write_bytes(mod._png_bytes(1024, 1536, bytearray(os.urandom(1024 * 1536 * 3))))
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"outputs": [{"path": str(expected)}]}), stderr="")

    path = mod.write_weather_image_with_model([cards[0]], now, tmp_path, day_kind=day_kind, command_runner=fake_run)

    assert path == expected
    assert calls
    assert calls[0][:5] == ["openclaw", "infer", "image", "generate", "--model"]
    assert "openai/gpt-image-2" in calls[0]
    assert "1024x1536" in calls[0]


def test_model_image_generation_uses_openai_compatible_http_endpoint(tmp_path: Path, monkeypatch) -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)
    generated_png = mod._png_bytes(1024, 1536, bytearray(os.urandom(1024 * 1536 * 3)))
    requests = []
    monkeypatch.setenv("OPENCLAW_PUBLIC_MODEL_BASE_URL", "http://ccnode.briconbric.com:49530/v1")
    monkeypatch.setenv("OPENCLAW_PUBLIC_MODEL_API_KEY", "test-key")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return json.dumps({"data": [{"b64_json": base64.b64encode(generated_png).decode("ascii")}]}).encode("utf-8")

    def fake_urlopen(req, timeout):
        requests.append((req, timeout))
        return FakeResponse()

    def forbidden_run(*_args, **_kwargs):
        raise AssertionError("direct HTTP endpoint should bypass openclaw image CLI")

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)

    path = mod.write_weather_image_with_model([cards[0]], now, tmp_path, day_kind=day_kind, command_runner=forbidden_run)

    assert path.is_file()
    assert requests
    assert requests[0][0].full_url == "http://ccnode.briconbric.com:49530/v1/images/generations"


def test_generate_weather_image_reply_falls_back_to_text_on_fetch_error(monkeypatch, tmp_path: Path) -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    monkeypatch.setenv("OPENCLAW_WEATHER_IMAGE_RETRIES", "1")

    def broken_fetch_json(_url: str) -> dict:
        raise RuntimeError("weather source unreachable")

    result = mod.generate_weather_image_reply(now=now, fetch_json=broken_fetch_json, output_dir=tmp_path)
    assert "天气预报" in result
    assert "天气服务暂时不可用" in result


def test_weather_image_locations_are_three_city_forecast_spec() -> None:
    assert [(loc.label, loc.area) for loc in mod.WEATHER_IMAGE_LOCATIONS] == [
        ("東京", "東京"),
        ("北京", "北京"),
        ("大连", "大连"),
    ]


def test_weather_image_main_fails_when_only_text_fallback_is_available(monkeypatch, capsys) -> None:
    monkeypatch.setattr(mod, "generate_weather_image_reply", lambda: "天气预报\n- 天气服务暂时不可用")

    assert mod.main() == 1
    assert "天气服务暂时不可用" in capsys.readouterr().out


def test_fetch_weather_card_reads_air_quality_from_shared_payload() -> None:
    card = mod.fetch_weather_card(mod.WEATHER_IMAGE_LOCATIONS[0], fetch_json=fake_fetch_json)

    assert card.aqi == 36


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

    assert "vertical 3:4 1024x1536" in prompt
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
    assert "unified clean modern CJK sans-serif typography system" in prompt
    assert "consistent font family, weight, spacing, and layout" in prompt
    assert "date in very small type" in prompt
    assert "temperature range in medium type" in prompt
    assert 'temperature label EXACTLY "17-27°C"' in prompt
    assert "daily minimum hyphen daily maximum" in prompt
    assert "do not show current temperature" in prompt
    assert "東京" in prompt


def test_temperature_label_uses_one_fixed_min_max_format() -> None:
    card = mod.WeatherCard("東京", "東京", "東京", "tokyo tower", 22, 2, 30, 12, 4, 36, 27, 17, "ok")

    assert mod.temperature_range_label(card) == "17-27°C"

    prompt = mod.build_image_prompt([card], datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo")), "weekday")
    assert 'temperature label EXACTLY "17-27°C"' in prompt
    assert "22°C" not in prompt


def test_model_output_is_normalized_to_formal_vertical_aspect(tmp_path: Path) -> None:
    try:
        from PIL import Image
    except Exception:
        return
    path = tmp_path / "model.png"
    Image.new("RGB", (1024, 1024), (240, 244, 250)).save(path)

    mod.normalize_png_aspect(path)

    with Image.open(path) as image:
        assert image.size == (1024, 1536)


def test_stdlib_png_normalizer_crops_truecolor_png(tmp_path: Path) -> None:
    path = tmp_path / "stdlib.png"
    pixels = bytearray([240, 244, 250] * (1024 * 2048))
    path.write_bytes(mod._png_bytes(1024, 2048, pixels))

    mod._normalize_png_aspect_stdlib(path, target_width=1024, target_height=1536)

    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    import struct

    assert struct.unpack(">II", data[16:24]) == (1024, 1536)


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


def test_model_image_generation_uses_explicit_candidate_fallback(tmp_path: Path, monkeypatch) -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)
    monkeypatch.setenv("OPENCLAW_WEATHER_IMAGE_MODEL_CANDIDATES", "openai/gpt-image-2,fallback")
    monkeypatch.setenv("OPENCLAW_WEATHER_ALLOW_DETERMINISTIC_FALLBACK", "1")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="endpoint not supported")

    path = mod.write_weather_image_with_model([cards[0]], now, tmp_path, day_kind=day_kind, command_runner=fake_run)

    assert path.is_file()
    assert path.name.endswith(".png")
    assert not path.name.endswith("_image2.png")


def test_candidate_fallback_is_not_delivered_without_explicit_permission(tmp_path: Path, monkeypatch) -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)
    monkeypatch.setenv("OPENCLAW_WEATHER_IMAGE_MODEL_CANDIDATES", "openai/gpt-image-2,fallback")
    monkeypatch.delenv("OPENCLAW_WEATHER_ALLOW_DETERMINISTIC_FALLBACK", raising=False)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="endpoint not supported")

    try:
        mod.write_weather_image_with_model([cards[0]], now, tmp_path, day_kind=day_kind, command_runner=fake_run)
    except RuntimeError as exc:
        assert "image provider unavailable" in str(exc)
    else:
        raise AssertionError("public weather jobs must not publish deterministic fallback images")


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
        if len(calls) in {1, 3}:
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"outputs": [{"path": str(generated)}]}), stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="model timeout")

    try:
        mod.write_weather_images_with_model(cards, now, tmp_path, day_kind=day_kind, command_runner=fake_run)
    except RuntimeError as exc:
        assert "refusing partial delivery" in str(exc)
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


def test_model_image_generation_retries_timeout(tmp_path: Path, monkeypatch) -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)
    generated = tmp_path / "retry.png"
    generated.write_bytes(mod._png_bytes(1024, 1536, bytearray(os.urandom(1024 * 1536 * 3))))
    calls = []
    monkeypatch.setenv("OPENCLAW_WEATHER_IMAGE_RETRIES", "2")

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="[image-generation] candidate failed: request timed out\n- plugins.allow: plugin not installed: line")
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"outputs": [{"path": str(generated)}]}), stderr="")

    path = mod.write_weather_image_with_model([cards[0]], now, tmp_path, day_kind=day_kind, command_runner=fake_run)

    assert path == generated
    assert len(calls) == 2
    assert "360000" in calls[0]


def test_model_image_generation_stops_retrying_non_retryable_provider_error(tmp_path: Path, monkeypatch) -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)
    calls = []
    monkeypatch.setenv("OPENCLAW_WEATHER_IMAGE_RETRIES", "3")

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout="",
            stderr="[image-generation] candidate failed: openai/gpt-image-2: OpenAI image generation failed (HTTP 404): endpoint not supported",
        )

    try:
        mod.write_weather_image_with_model([cards[0]], now, tmp_path, day_kind=day_kind, command_runner=fake_run)
    except RuntimeError as exc:
        assert "endpoint not supported" in str(exc)
        assert "image provider unavailable" in str(exc)
    else:
        raise AssertionError("non-retryable provider errors must fail clearly")

    assert len(calls) == 1


def test_weather_image_model_candidates_try_next_configured_model(tmp_path: Path, monkeypatch) -> None:
    now = datetime(2026, 5, 19, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    cards, _rest_day, day_kind = mod.build_cards(now, fetch_json=fake_fetch_json)
    generated = tmp_path / "candidate.png"
    generated.write_bytes(mod._png_bytes(1024, 1536, bytearray(os.urandom(1024 * 1536 * 3))))
    calls = []
    monkeypatch.setenv("OPENCLAW_WEATHER_IMAGE_MODEL_CANDIDATES", "openai/bad-image,openai/gpt-image-2")

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="model_not_available")
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"outputs": [{"path": str(generated)}]}), stderr="")

    path = mod.write_weather_image_with_model([cards[0]], now, tmp_path, day_kind=day_kind, command_runner=fake_run)

    assert path == generated
    assert "openai/bad-image" in calls[0]
    assert "openai/gpt-image-2" in calls[1]


def test_image_error_summary_filters_plugin_noise() -> None:
    summary = mod._summarize_image_error(
        "[image-generation] candidate failed: openai/gpt-image-2: request timed out\n"
        "- plugins.allow: plugin not installed: line\n"
        "TimeoutError: request timed out\n"
    )

    assert "request timed out" in summary
    assert "plugin not installed" not in summary

if __name__ == "__main__":
    raise SystemExit(main())
