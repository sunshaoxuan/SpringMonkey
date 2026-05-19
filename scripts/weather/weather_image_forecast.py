#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import math
import os
import struct
import subprocess
import urllib.parse
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import discord_weather_report as report

TZ = ZoneInfo("Asia/Tokyo")
DEFAULT_OUTPUT_DIR = Path("/var/lib/openclaw/.openclaw/workspace/media/weather")
DEFAULT_IMAGE_MODEL = "openai/gpt-image-2"
TARGET_IMAGE_WIDTH = 1024
TARGET_IMAGE_HEIGHT = 1365

@dataclass(frozen=True)
class WeatherCard:
    label: str
    area: str
    city: str
    landmark_hint: str
    temperature_c: float | None
    weather_code: int | None
    precipitation_probability: float | None
    wind_kmh: float | None
    uv_index: float | None
    aqi: float | int | None
    temp_max_c: float | None
    temp_min_c: float | None
    advice: str

def _fmt(value: float | int | None, suffix: str = "", digits: int = 0) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.{digits}f}{suffix}" if digits else f"{int(round(float(value)))}{suffix}"

def _city_for_area(area: str) -> tuple[str, str]:
    if "杉並" in area or "東京" in area or "品川" in area or "川口" in area or "埼玉" in area:
        return "東京", "Tokyo landmark skyline, compact neighborhood streets, riverside bridges, and station plaza"
    return area, "local skyline and compact streets"

def fetch_weather_card(location: report.Location, *, fetch_json=report.fetch_json) -> WeatherCard:
    forecast_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": location.latitude, "longitude": location.longitude, "timezone": "Asia/Tokyo",
        "current": "temperature_2m,weather_code,precipitation,wind_speed_10m,uv_index",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "forecast_days": 2,
    })
    air_url = "https://air-quality-api.open-meteo.com/v1/air-quality?" + urllib.parse.urlencode({
        "latitude": location.latitude, "longitude": location.longitude, "timezone": "Asia/Tokyo", "current": "us_aqi",
    })
    forecast = fetch_json(forecast_url)
    try:
        air = fetch_json(air_url)
    except Exception:
        air = {"current": {"us_aqi": None}}
    current = forecast.get("current", {}) if isinstance(forecast.get("current"), dict) else {}
    daily = forecast.get("daily", {}) if isinstance(forecast.get("daily"), dict) else {}
    temp = current.get("temperature_2m"); precip = current.get("precipitation"); wind = current.get("wind_speed_10m")
    precip_prob = (daily.get("precipitation_probability_max") or [None])[0]
    city, landmark_hint = _city_for_area(location.area)
    return WeatherCard(
        label=location.label, area=location.area, city=city, landmark_hint=landmark_hint,
        temperature_c=temp, weather_code=current.get("weather_code"), precipitation_probability=precip_prob,
        wind_kmh=wind, uv_index=current.get("uv_index"), aqi=(air.get("current") or {}).get("us_aqi") if isinstance(air, dict) else None,
        temp_max_c=(daily.get("temperature_2m_max") or [None])[0], temp_min_c=(daily.get("temperature_2m_min") or [None])[0],
        advice=report.traffic_advice(precip, precip_prob, wind, temp),
    )

def weather_icon(code: int | None) -> str:
    if code in {0, 1}: return "☀️"
    if code in {2, 3, 45, 48}: return "☁️"
    if code in {51, 53, 55, 61, 63, 65, 80, 81, 82}: return "🌧️"
    if code in {71, 73, 75, 77, 85, 86}: return "❄️"
    if code in {95, 96, 99}: return "⛈️"
    return "🌤️"

def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)

def _building_svg(x: int, y: int, w: int, h: int, color: str, side: str = "#6b7a99") -> str:
    return f'<polygon points="{x},{y} {x+w},{y-18} {x+w},{y+h-18} {x},{y+h}" fill="{color}"/><polygon points="{x+w},{y-18} {x+w+24},{y-6} {x+w+24},{y+h+12} {x+w},{y+h-18}" fill="{side}"/><polygon points="{x},{y} {x+w},{y-18} {x+w+24},{y-6} {x+24},{y+12}" fill="#d7e4ff" opacity="0.7"/>'

def _scene_svg(card: WeatherCard, *, x: int, theme: str) -> str:
    sky = "#ffe6a7" if card.weather_code in {0, 1, 2} else "#dbe7f5"
    ground = "#9bd18b" if theme == "green" else "#91c7d9"
    tower_color = "#ef8354" if card.city == "Tokyo" else "#6d8ccf"
    label = f"{card.label} · {card.area}"
    return f'''<g transform="translate({x},150)"><rect x="0" y="0" width="520" height="620" rx="34" fill="{sky}" opacity="0.95"/><ellipse cx="260" cy="435" rx="205" ry="78" fill="{ground}"/><path d="M120 430 L260 350 L405 430 L260 510 Z" fill="#c8f0b6" stroke="#6aa66f" stroke-width="3"/>{_building_svg(160,330,58,110,'#7da0d6')}{_building_svg(250,300,70,145,'#8fb3e7')}{_building_svg(335,345,48,88,'#7593c7')}<polygon points="248,330 284,160 322,330" fill="{tower_color}"/><polygon points="262,260 307,260 294,306 270,306" fill="#ffe9c7" opacity="0.78"/><rect x="232" y="410" width="95" height="26" rx="12" fill="#67748f"/><path d="M105 448 C170 420, 220 470, 280 445 S390 435, 430 470" fill="none" stroke="#67a7df" stroke-width="18" opacity="0.55"/><circle cx="405" cy="95" r="42" fill="#fff7b2" opacity="0.9"/><text x="48" y="72" font-family="Inter, system-ui, sans-serif" font-size="30" font-weight="800" fill="#21304f">{_esc(label)}</text><text x="48" y="116" font-family="Inter, system-ui, sans-serif" font-size="28" fill="#21304f">{weather_icon(card.weather_code)} {_esc(report.weather_label(card.weather_code))}  {_fmt(card.temperature_c, '°C')}</text><text x="48" y="532" font-family="Inter, system-ui, sans-serif" font-size="23" fill="#21304f">最高 {_fmt(card.temp_max_c, '°C')} / 最低 {_fmt(card.temp_min_c, '°C')} · 降水 {_fmt(card.precipitation_probability, '%')}</text><text x="48" y="570" font-family="Inter, system-ui, sans-serif" font-size="21" fill="#21304f">风 {_fmt(card.wind_kmh, 'km/h')} · UV {_fmt(card.uv_index)} · AQI {_fmt(card.aqi)}</text></g>'''

def render_svg(cards: list[WeatherCard], now: datetime) -> str:
    cards = cards[:2] or []
    while len(cards) < 2:
        cards.append(cards[0])
    source_note = "Data source: Open-Meteo weather and air-quality APIs. Visual: deterministic 3D miniature cityscape, no logos or brand marks."
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="900" viewBox="0 0 1280 900" role="img" aria-label="3D miniature weather forecast"><defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#eef7ff"/><stop offset="1" stop-color="#f8efe4"/></linearGradient><filter id="shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="18" stdDeviation="18" flood-color="#34415f" flood-opacity="0.25"/></filter></defs><rect width="1280" height="900" fill="url(#bg)"/><text x="640" y="72" text-anchor="middle" font-family="Inter, system-ui, sans-serif" font-size="44" font-weight="900" fill="#1c2942">天气预报 3D 微缩景观</text><text x="640" y="112" text-anchor="middle" font-family="Inter, system-ui, sans-serif" font-size="23" fill="#53627d">{now:%Y-%m-%d %H:%M JST} · 两地城市地标风格 · 私有工作流生成</text><g filter="url(#shadow)">{_scene_svg(cards[0], x=90, theme='green')}{_scene_svg(cards[1], x=670, theme='blue')}</g><rect x="90" y="805" width="1100" height="54" rx="18" fill="#ffffff" opacity="0.82"/><text x="112" y="840" font-family="Inter, system-ui, sans-serif" font-size="18" fill="#53627d">{_esc(source_note)}</text></svg>\n'''


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


class Raster:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray(width * height * 3)

    def set(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            i = (y * self.width + x) * 3
            self.pixels[i : i + 3] = bytes(color)

    def rect(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int]) -> None:
        for yy in range(max(0, y), min(self.height, y + h)):
            start = max(0, x)
            end = min(self.width, x + w)
            if start >= end:
                continue
            row = (yy * self.width + start) * 3
            self.pixels[row : row + (end - start) * 3] = bytes(color) * (end - start)

    def circle(self, cx: int, cy: int, r: int, color: tuple[int, int, int]) -> None:
        rr = r * r
        for y in range(cy - r, cy + r + 1):
            for x in range(cx - r, cx + r + 1):
                if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= rr:
                    self.set(x, y, color)

    def ellipse(self, cx: int, cy: int, rx: int, ry: int, color: tuple[int, int, int]) -> None:
        for y in range(cy - ry, cy + ry + 1):
            for x in range(cx - rx, cx + rx + 1):
                if ((x - cx) * (x - cx)) / max(1, rx * rx) + ((y - cy) * (y - cy)) / max(1, ry * ry) <= 1:
                    self.set(x, y, color)

    def polygon(self, points: list[tuple[int, int]], color: tuple[int, int, int]) -> None:
        min_x = max(0, min(x for x, _y in points))
        max_x = min(self.width - 1, max(x for x, _y in points))
        min_y = max(0, min(y for _x, y in points))
        max_y = min(self.height - 1, max(y for _x, y in points))
        for y in range(min_y, max_y + 1):
            inside = False
            j = len(points) - 1
            nodes: list[int] = []
            for i, (xi, yi) in enumerate(points):
                xj, yj = points[j]
                if (yi < y <= yj) or (yj < y <= yi):
                    nodes.append(int(xi + (y - yi) / (yj - yi) * (xj - xi)))
                j = i
            nodes.sort()
            for a, b in zip(nodes[::2], nodes[1::2]):
                for x in range(max(min_x, a), min(max_x, b) + 1):
                    self.set(x, y, color)


def _png_bytes(width: int, height: int, pixels: bytearray) -> bytes:
    raw = b"".join(b"\x00" + pixels[y * width * 3 : (y + 1) * width * 3] for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def _draw_card(r: Raster, card: WeatherCard, x: int, y: int, theme: str) -> None:
    sky = _rgb("#ffe6a7") if card.weather_code in {0, 1, 2} else _rgb("#dbe7f5")
    ground = _rgb("#9bd18b") if theme == "green" else _rgb("#91c7d9")
    tower = _rgb("#ef8354") if card.city == "Tokyo" else _rgb("#6d8ccf")
    r.rect(x + 8, y + 12, 504, 504, _rgb("#d2d7e4"))
    r.rect(x, y, 504, 504, sky)
    r.circle(x + 410, y + 82, 42, _rgb("#fff1a1"))
    r.ellipse(x + 252, y + 370, 190, 70, ground)
    r.polygon([(x + 112, y + 360), (x + 252, y + 290), (x + 392, y + 360), (x + 252, y + 440)], _rgb("#c8f0b6"))
    r.polygon([(x + 82, y + 408), (x + 180, y + 382), (x + 270, y + 420), (x + 420, y + 398), (x + 450, y + 428), (x + 275, y + 458), (x + 150, y + 430)], _rgb("#67a7df"))
    for bx, by, bw, bh, color in [
        (150, 270, 55, 128, "#7da0d6"),
        (238, 230, 74, 168, "#8fb3e7"),
        (328, 300, 58, 98, "#7593c7"),
    ]:
        r.polygon([(x + bx, y + by), (x + bx + bw, y + by - 18), (x + bx + bw, y + by + bh - 18), (x + bx, y + by + bh)], _rgb(color))
        r.polygon([(x + bx + bw, y + by - 18), (x + bx + bw + 24, y + by - 5), (x + bx + bw + 24, y + by + bh + 12), (x + bx + bw, y + by + bh - 18)], _rgb("#647695"))
    r.polygon([(x + 238, y + 270), (x + 276, y + 104), (x + 318, y + 270)], tower)
    r.rect(x + 218, y + 408, 96, 24, _rgb("#67748f"))
    temp_bar = max(20, min(180, int((card.temperature_c or 20) * 5)))
    r.rect(x + 54, y + 48, temp_bar, 18, _rgb("#21304f"))
    rain_bar = max(12, min(180, int((card.precipitation_probability or 0) * 1.8)))
    r.rect(x + 54, y + 82, rain_bar, 14, _rgb("#2f80ed"))


def render_png(cards: list[WeatherCard], now: datetime) -> bytes:
    cards = cards[:2] or []
    if not cards:
        raise ValueError("at least one weather card is required")
    width, height = 1024, 1365
    r = Raster(width, height)
    for y in range(height):
        mix = y / height
        c = (
            int(238 * (1 - mix) + 248 * mix),
            int(247 * (1 - mix) + 239 * mix),
            int(255 * (1 - mix) + 228 * mix),
        )
        r.rect(0, y, width, 1, c)
    if len(cards) == 1:
        _draw_card(r, cards[0], 260, 420, "green")
    else:
        _draw_card(r, cards[0], 84, 420, "green")
        _draw_card(r, cards[1], 516, 420, "blue")
    return _png_bytes(width, height, r.pixels)


def write_weather_image(cards: list[WeatherCard], now: datetime | None = None, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    now = now or datetime.now(TZ)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"weather_miniature_{now:%Y%m%d_%H%M%S}.png"
    path.write_bytes(render_png(cards, now))
    return path


def build_image_prompt(cards: list[WeatherCard], now: datetime, day_kind: str) -> str:
    summaries = []
    for card in cards:
        summaries.append(
            f"{card.city}: {report.weather_label(card.weather_code)}, {_fmt(card.temperature_c, '°C')}, "
            f"high {_fmt(card.temp_max_c, '°C')}, low {_fmt(card.temp_min_c, '°C')}, "
            f"rain probability {_fmt(card.precipitation_probability, '%')}, wind {_fmt(card.wind_kmh, 'km/h')}; "
            f"landmark reference: {card.landmark_hint}"
        )
    scene_count = "one city scene" if len(cards) == 1 else f"{len(cards)} separate city scenes"
    return (
        "Create a premium weather forecast image as a single finished picture, not a UI mockup. "
        f"Use a vertical 3:4 centered composition with {scene_count}. "
        "If multiple people are in the same city, merge them into one city forecast scene; only add another scene when a distinct city exists. "
        "Camera and scene: clear 45-degree top-down isometric view, cute 3D chibi miniature city landmark diorama, "
        "main building centered, precise toy-like architectural details, warm tactile PBR materials, soft realistic lighting and shadows. "
        "Composition: clean, unified, fresh, comfortable, minimal pure-color soft background, no panels, no cards, no text boxes. "
        "Weather integration: weather effects must be integrated into the city architecture and interact with the scene, "
        "for example sun, clouds, rain, wind, mist, puddles, reflections, or atmospheric particles around the buildings. "
        "Typography inside the image: at the very top show a large city name in the same written language as the city name; "
        "directly below or near it show a prominent weather icon; under the icon show the date in very small type and the temperature range in medium type. "
        "Weather text has no background and may overlap or blend with the buildings naturally. "
        f"Forecast date: {now:%Y-%m-%d} ({day_kind}). Forecast data: {'; '.join(summaries)}. "
        "No extra caption outside the image, no brand logos, no watermarks, no copyrighted characters, no unreadable clutter."
    )


def generate_model_image(
    cards: list[WeatherCard],
    now: datetime,
    day_kind: str,
    output_dir: Path,
    *,
    model: str = DEFAULT_IMAGE_MODEL,
    command_runner=subprocess.run,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"weather_miniature_{now:%Y%m%d_%H%M%S}_image2.png"
    cmd = [
        "openclaw",
        "infer",
        "image",
        "generate",
        "--model",
        model,
        "--prompt",
        build_image_prompt(cards, now, day_kind),
        "--size",
        "1024x1365",
        "--output-format",
        "png",
        "--output",
        str(path),
        "--timeout-ms",
        "180000",
        "--json",
    ]
    env = os.environ.copy()
    env.setdefault("HOME", "/var/lib/openclaw")
    proc = command_runner(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=240,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or f"image generation failed: {proc.returncode}")[-1000:])
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"image generation returned invalid JSON: {exc}") from exc
    outputs = payload.get("outputs") if isinstance(payload, dict) else None
    first = outputs[0] if isinstance(outputs, list) and outputs else {}
    generated = Path(str(first.get("path") or path))
    if not generated.is_file():
        raise RuntimeError(f"image generation did not create output file: {generated}")
    if generated.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"image generation output is not PNG: {generated}")
    normalize_png_aspect(generated, target_width=TARGET_IMAGE_WIDTH, target_height=TARGET_IMAGE_HEIGHT)
    return generated


def normalize_png_aspect(path: Path, *, target_width: int = TARGET_IMAGE_WIDTH, target_height: int = TARGET_IMAGE_HEIGHT) -> None:
    try:
        from PIL import Image
    except Exception:
        _normalize_png_aspect_stdlib(path, target_width=target_width, target_height=target_height)
        return
    with Image.open(path) as image:
        if image.size == (target_width, target_height):
            return
        if image.width != target_width:
            new_height = max(1, round(image.height * (target_width / image.width)))
            image = image.resize((target_width, new_height))
        if image.height > target_height:
            # Keep the top typography and city landmark focal area; trim excess
            # from the bottom when the image API coerces 3:4 to 1024x1536.
            image = image.crop((0, 0, target_width, target_height))
        elif image.height < target_height:
            canvas = Image.new("RGB", (target_width, target_height), image.getpixel((0, image.height - 1)) if image.height else (248, 247, 244))
            canvas.paste(image.convert("RGB"), (0, 0))
            image = canvas
        image.save(path, format="PNG")


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return []
    chunks: list[tuple[bytes, bytes]] = []
    pos = 8
    while pos + 8 <= len(data):
        size = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        payload = data[pos + 8 : pos + 8 + size]
        chunks.append((kind, payload))
        pos += 12 + size
        if kind == b"IEND":
            break
    return chunks


def _normalize_png_aspect_stdlib(path: Path, *, target_width: int, target_height: int) -> None:
    data = path.read_bytes()
    chunks = _png_chunks(data)
    if not chunks:
        return
    ihdr = next((payload for kind, payload in chunks if kind == b"IHDR"), None)
    if not ihdr:
        return
    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(">IIBBBBB", ihdr)
    if (width, height) == (target_width, target_height):
        return
    if width != target_width or height <= target_height:
        return
    if bit_depth != 8 or color_type != 2 or compression != 0 or filter_method != 0 or interlace != 0:
        return
    idat = b"".join(payload for kind, payload in chunks if kind == b"IDAT")
    if not idat:
        return
    try:
        raw = zlib.decompress(idat)
    except zlib.error:
        return
    bpp = 3
    row_len = width * bpp
    expected = (row_len + 1) * height
    if len(raw) < expected:
        return
    rows: list[bytearray] = []
    prev = bytearray(row_len)
    offset = 0
    for _row in range(height):
        filter_type = raw[offset]
        encoded = bytearray(raw[offset + 1 : offset + 1 + row_len])
        offset += row_len + 1
        recon = bytearray(row_len)
        for i, value in enumerate(encoded):
            left = recon[i - bpp] if i >= bpp else 0
            up = prev[i]
            upper_left = prev[i - bpp] if i >= bpp else 0
            if filter_type == 0:
                recon[i] = value
            elif filter_type == 1:
                recon[i] = (value + left) & 0xFF
            elif filter_type == 2:
                recon[i] = (value + up) & 0xFF
            elif filter_type == 3:
                recon[i] = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                recon[i] = (value + _paeth(left, up, upper_left)) & 0xFF
            else:
                return
        rows.append(recon)
        prev = recon
    cropped = rows[:target_height]
    packed = b"".join(b"\x00" + bytes(row) for row in cropped)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", target_width, target_height, bit_depth, color_type, compression, filter_method, interlace))
        + _png_chunk(b"IDAT", zlib.compress(packed, 6))
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def write_weather_image_with_model(
    cards: list[WeatherCard],
    now: datetime | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    day_kind: str = "",
    model: str | None = None,
    command_runner=subprocess.run,
) -> Path:
    now = now or datetime.now(TZ)
    selected_model = model if model is not None else os.environ.get("OPENCLAW_WEATHER_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)
    if selected_model and selected_model.lower() not in {"off", "none", "fallback"}:
        try:
            return generate_model_image(cards, now, day_kind or "平日", output_dir, model=selected_model, command_runner=command_runner)
        except Exception:
            # Deterministic fallback keeps the cron from failing, but the normal
            # path must be the configured image model.
            pass
    return write_weather_image(cards, now, output_dir)


def _avg(values: list[float | int | None], *, digits: int = 1) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    if not numeric:
        return None
    return round(sum(numeric) / len(numeric), digits)


def _max(values: list[float | int | None]) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    return max(numeric) if numeric else None


def _min(values: list[float | int | None]) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    return min(numeric) if numeric else None


def _representative_weather_code(cards: list[WeatherCard]) -> int | None:
    if not cards:
        return None
    rainy = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}
    snowy = {71, 73, 75, 77, 85, 86}
    for group in (rainy, snowy):
        for card in cards:
            if card.weather_code in group:
                return card.weather_code
    return cards[0].weather_code


def group_cards_by_city(cards: list[WeatherCard]) -> dict[str, list[WeatherCard]]:
    grouped: dict[str, list[WeatherCard]] = {}
    for card in cards:
        grouped.setdefault(card.city, []).append(card)
    return grouped


def merge_same_city_cards(cards: list[WeatherCard]) -> list[WeatherCard]:
    merged: list[WeatherCard] = []
    for city, group in group_cards_by_city(cards).items():
        if len(group) == 1:
            merged.append(group[0])
            continue
        areas = "、".join(dict.fromkeys(card.area for card in group))
        hints = "; ".join(dict.fromkeys(card.landmark_hint for card in group))
        merged.append(
            WeatherCard(
                label=city,
                area=areas,
                city=city,
                landmark_hint=hints,
                temperature_c=_avg([card.temperature_c for card in group]),
                weather_code=_representative_weather_code(group),
                precipitation_probability=_max([card.precipitation_probability for card in group]),
                wind_kmh=_avg([card.wind_kmh for card in group]),
                uv_index=_max([card.uv_index for card in group]),
                aqi=_max([card.aqi for card in group]),
                temp_max_c=_max([card.temp_max_c for card in group]),
                temp_min_c=_min([card.temp_min_c for card in group]),
                advice=" / ".join(dict.fromkeys(card.advice for card in group if card.advice)),
            )
        )
    return merged


def build_cards(now: datetime | None = None, *, fetch_json=report.fetch_json) -> tuple[list[WeatherCard], bool, str]:
    now = now or datetime.now(TZ)
    locations, rest_day, day_kind = report.locations_for_day(now)
    cards = [fetch_weather_card(loc, fetch_json=fetch_json) for loc in locations]
    return merge_same_city_cards(cards), rest_day, day_kind

def build_media_reply(path: Path, cards: list[WeatherCard], now: datetime, day_kind: str) -> str:
    return f"MEDIA:{path}"

def generate_weather_image_reply(now: datetime | None = None, *, fetch_json=report.fetch_json, output_dir: Path = DEFAULT_OUTPUT_DIR) -> str:
    now = now or datetime.now(TZ)
    cards, _rest_day, day_kind = build_cards(now, fetch_json=fetch_json)
    path = write_weather_image_with_model(cards, now, output_dir, day_kind=day_kind)
    return build_media_reply(path, cards, now, day_kind)

def main() -> int:
    print(generate_weather_image_reply())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
