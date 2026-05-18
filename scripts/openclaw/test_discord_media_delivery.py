from __future__ import annotations

import json
from pathlib import Path

import discord_media_delivery as media


def test_parse_media_reply_extracts_file_and_caption(tmp_path: Path) -> None:
    image = tmp_path / "weather.svg"
    image.write_text("<svg/>", encoding="utf-8")

    parsed = media.parse_media_reply(f"MEDIA:{image}\n天气预报图片\n数据源：Open-Meteo")

    assert parsed is not None
    assert parsed.media_path == image
    assert parsed.caption == "天气预报图片\n数据源：Open-Meteo"


def test_parse_media_reply_ignores_missing_file() -> None:
    assert media.parse_media_reply("MEDIA:/missing/weather.svg\ncaption") is None


def test_multipart_body_contains_payload_and_file(tmp_path: Path) -> None:
    image = tmp_path / "weather.svg"
    image.write_text("<svg>weather</svg>", encoding="utf-8")

    body = media._multipart_body(
        payload={"content": "caption", "attachments": [{"id": 0, "filename": image.name}]},
        file_path=image,
        boundary="BOUNDARY",
    )

    assert b'name="payload_json"' in body
    assert b'name="files[0]"; filename="weather.svg"' in body
    assert b"<svg>weather</svg>" in body
    payload_part = body.split(b"\r\n\r\n", 1)[1].split(b"\r\n", 1)[0]
    assert json.loads(payload_part.decode("utf-8"))["content"] == "caption"
