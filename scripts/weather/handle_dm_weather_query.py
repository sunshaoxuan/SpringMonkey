#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from pathlib import Path
import discord_weather_report as weather_report

_OPENCLAW_DIR = Path(__file__).resolve().parents[1] / "openclaw"
if str(_OPENCLAW_DIR) not in sys.path:
    sys.path.insert(0, str(_OPENCLAW_DIR))

from model_fallback_client import chat_with_fallback


TZ = ZoneInfo("Asia/Tokyo")

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


@dataclass(frozen=True)
class Location:
    name: str
    latitude: float
    longitude: float


KNOWN_LOCATIONS = {
    "东京": Location("东京", 35.6762, 139.6503),
    "東京": Location("东京", 35.6762, 139.6503),
    "tokyo": Location("东京", 35.6762, 139.6503),
    "长野": Location("长野", 36.6486, 138.1948),
    "長野": Location("长野", 36.6486, 138.1948),
    "nagano": Location("长野", 36.6486, 138.1948),
}

WEATHER_TEXT = {
    0: "晴朗",
    1: "大致晴朗",
    2: "晴间多云",
    3: "多云",
    45: "有雾",
    48: "冻雾",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    61: "小雨",
    63: "降雨",
    65: "大雨",
    71: "小雪",
    73: "降雪",
    75: "大雪",
    80: "阵雨",
    81: "强阵雨",
    82: "暴雨阵雨",
    95: "雷雨",
}


def parse_message_time(raw: str) -> datetime:
    value = datetime.fromisoformat((raw or "").replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=TZ)
    return value.astimezone(TZ)


def extract_json_object(text: str) -> dict:
    raw = (text or "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"模型未返回天气查询 JSON 契约：{raw[:160]}")
    data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("模型返回的天气查询契约不是 JSON object")
    return data


def classify_weather_contract(text: str, message_timestamp: str, model_caller=None) -> dict:
    base = parse_message_time(message_timestamp)
    system = (
        "You are a semantic contract parser for a read-only weather executor. "
        "Classify by meaning, not keyword matching. Return strict JSON only. "
        "Schema: {supported:boolean, date_local:string|null, locations:[string], confidence:number, reason:string}. "
        "date_local must be YYYY-MM-DD in Asia/Tokyo. "
        "locations must use only registered names from: 东京, 长野. "
        "If the request is not a concrete weather query for registered locations, supported=false."
    )
    user = json.dumps(
        {
            "message_time": base.isoformat(timespec="minutes"),
            "user_text": text,
            "registered_locations": sorted({loc.name for loc in KNOWN_LOCATIONS.values()}),
        },
        ensure_ascii=False,
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    content = model_caller(messages) if model_caller else chat_with_fallback(messages, timeout=30, temperature=0)[0]
    contract = extract_json_object(content)
    if not bool(contract.get("supported")):
        raise ValueError(str(contract.get("reason") or "模型判断该指令不是受支持的天气查询契约"))
    if float(contract.get("confidence") or 0.0) < 0.65:
        raise ValueError("天气查询契约置信度过低")
    names = contract.get("locations") if isinstance(contract.get("locations"), list) else []
    if not names:
        raise ValueError("天气查询契约缺少地点")
    for name in names:
        if str(name) not in {loc.name for loc in KNOWN_LOCATIONS.values()}:
            raise ValueError(f"天气查询契约包含未注册地点：{name}")
    if not contract.get("date_local"):
        raise ValueError("天气查询契约缺少 date_local")
    return contract


def locations_from_contract(names: list[str]) -> list[Location]:
    by_name = {loc.name: loc for loc in KNOWN_LOCATIONS.values()}
    result: list[Location] = []
    seen: set[str] = set()
    for name in names:
        loc = by_name[str(name)]
        if loc.name not in seen:
            result.append(loc)
            seen.add(loc.name)
    return result


def fetch_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "OpenClawWeatherDm/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def weather_label(code: int | None) -> str:
    if code is None:
        return "不明"
    return WEATHER_TEXT.get(code, f"天气代码{code}")


def fmt(value: float | int | None, suffix: str = "", digits: int = 0) -> str:
    if value is None:
        return "N/A"
    if digits == 0:
        return f"{int(round(float(value)))}{suffix}"
    return f"{float(value):.{digits}f}{suffix}"


def _normalize_hourly_time(day: datetime, raw: str | None) -> str:
    if not raw:
        return ""
    value = str(raw).strip()
    if ":" in value:
        return value
    if value.count("-") >= 2:
        return value
    if value.isdigit():
        if len(value) == 2:
            return f"{day:%Y-%m-%d} {value}:00"
        if len(value) == 4:
            return f"{day:%Y-%m-%d} {value[:2]}:{value[2:]}"
    return value


def _value_matches_day(day: datetime, raw: str | None) -> bool:
    if not isinstance(raw, str):
        return False
    return raw.startswith(day.strftime("%Y-%m-%d")) or (":" in raw and len(raw) <= 5)


def values_for_day(hourly: dict, day: datetime, key: str) -> list[float]:
    times = hourly.get("time") or []
    values = hourly.get(key) or []
    result: list[float] = []
    for t, value in zip(times, values):
        if _value_matches_day(day, _normalize_hourly_time(day, t if isinstance(t, str) else "")) and value is not None:
            result.append(float(value))
    return result


def dominant_weather_code(hourly: dict, day: datetime) -> int | None:
    codes = values_for_day(hourly, day, "weather_code")
    if not codes:
        return None
    counts: dict[int, int] = {}
    for code in codes:
        counts[int(code)] = counts.get(int(code), 0) + 1
    return max(counts.items(), key=lambda item: item[1])[0]


def min_max(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    return min(values), max(values)


def fetch_location_weather(loc: Location, day: datetime) -> str:
    payload = weather_report.fetch_weather_payload(weather_report.Location(loc.name, loc.name, loc.latitude, loc.longitude), fetch_json=fetch_json)
    source = str(payload.get("source", "open-meteo"))
    hourly = payload.get("hourly") or {}
    temps = values_for_day(hourly, day, "temperature_2m")
    precip = values_for_day(hourly, day, "precipitation_probability")
    wind = values_for_day(hourly, day, "wind_speed_10m")
    gust = values_for_day(hourly, day, "wind_gusts_10m")
    visibility = values_for_day(hourly, day, "visibility")

    tmin, tmax = min_max(temps)
    vmin, _vmax = min_max(visibility)
    code = dominant_weather_code(hourly, day)
    max_precip = max(precip) if precip else None
    max_wind = max(wind) if wind else None
    max_gust = max(gust) if gust else None
    visibility_km = None if vmin is None else vmin / 1000.0
    caution: list[str] = []
    if max_wind is not None and max_wind >= 35:
        caution.append("风偏强")
    if visibility_km is not None and visibility_km < 5:
        caution.append("能见度偏低")
    if max_precip is not None and max_precip >= 60:
        caution.append("降水概率较高")
    note = "；注意：" + "、".join(caution) if caution else "；无明显天气风险"
    return (
        f"- {loc.name}: {weather_label(code)}，"
        f"{fmt(tmin, '°C')}~{fmt(tmax, '°C')}，"
        f"最高降水概率{fmt(max_precip, '%')}，"
        f"最大风速{fmt(max_wind, 'km/h')}、阵风{fmt(max_gust, 'km/h')}，"
        f"最低能见度{fmt(visibility_km, 'km', 1)}{note}；数据源：{source}"
    )


def build_report(text: str, message_timestamp: str, *, model_caller=None) -> str:
    contract = classify_weather_contract(text, message_timestamp, model_caller=model_caller)
    day = datetime.fromisoformat(str(contract["date_local"])).replace(tzinfo=TZ)
    locations = locations_from_contract([str(item) for item in contract["locations"]])
    lines = [f"天气查询 {day:%Y-%m-%d}（亚洲/东京）"]
    for loc in locations:
        lines.append(fetch_location_weather(loc, day))
    lines.append("数据源：Open-Meteo；本次为私信只读查询，未改动任何系统状态。")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--message-timestamp", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(build_report(args.text, args.message_timestamp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
