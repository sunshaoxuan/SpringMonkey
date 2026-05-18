#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import discord_weather_report as report

TZ = ZoneInfo("Asia/Tokyo")
DEFAULT_OUTPUT_DIR = Path("/var/lib/openclaw/.openclaw/workspace/media/weather")

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
    if "杉並" in area or "東京" in area or "品川" in area:
        return "Tokyo", "tower skyline and neighborhood streets"
    if "川口" in area or "埼玉" in area:
        return "Kawaguchi", "river bridge, foundry town skyline, and compact station plaza"
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

def write_weather_image(cards: list[WeatherCard], now: datetime | None = None, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    now = now or datetime.now(TZ)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"weather_miniature_{now:%Y%m%d_%H%M%S}.svg"
    path.write_text(render_svg(cards, now), encoding="utf-8")
    return path

def build_cards(now: datetime | None = None, *, fetch_json=report.fetch_json) -> tuple[list[WeatherCard], bool, str]:
    now = now or datetime.now(TZ)
    locations, rest_day, day_kind = report.locations_for_day(now)
    return [fetch_weather_card(loc, fetch_json=fetch_json) for loc in locations[:2]], rest_day, day_kind

def build_media_reply(path: Path, cards: list[WeatherCard], now: datetime, day_kind: str) -> str:
    summary = " / ".join(f"{card.area}{_fmt(card.temperature_c, '°C')} {report.weather_label(card.weather_code)}" for card in cards[:2])
    return "\n".join([f"MEDIA:{path}", f"天气预报图片 {now:%Y-%m-%d}（{day_kind}）：{summary}", "数据源：Open-Meteo；视觉为无品牌、无水印的 3D 微缩景观式天气卡。"])

def generate_weather_image_reply(now: datetime | None = None, *, fetch_json=report.fetch_json, output_dir: Path = DEFAULT_OUTPUT_DIR) -> str:
    now = now or datetime.now(TZ)
    cards, _rest_day, day_kind = build_cards(now, fetch_json=fetch_json)
    return build_media_reply(write_weather_image(cards, now, output_dir), cards, now, day_kind)

def main() -> int:
    print(generate_weather_image_reply())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
