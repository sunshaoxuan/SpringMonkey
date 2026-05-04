#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


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


def target_date(text: str, message_timestamp: str) -> datetime:
    base = parse_message_time(message_timestamp)
    compact = re.sub(r"\s+", "", text or "").lower()
    if "后天" in compact or "明後日" in compact:
        return base + timedelta(days=2)
    if "今天" in compact or "今日" in compact:
        return base
    return base + timedelta(days=1)


def extract_locations(text: str) -> list[Location]:
    lowered = (text or "").lower()
    found: list[Location] = []
    seen: set[str] = set()
    for key, loc in KNOWN_LOCATIONS.items():
        if key.lower() in lowered and loc.name not in seen:
            found.append(loc)
            seen.add(loc.name)
    if found:
        return found
    raise ValueError("无法从指令中识别地点；当前已注册：东京、长野")


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


def values_for_day(hourly: dict, day: datetime, key: str) -> list[float]:
    times = hourly.get("time") or []
    values = hourly.get(key) or []
    prefix = day.strftime("%Y-%m-%d")
    result: list[float] = []
    for t, value in zip(times, values):
        if isinstance(t, str) and t.startswith(prefix) and value is not None:
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
    query = urllib.parse.urlencode(
        {
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "timezone": "Asia/Tokyo",
            "forecast_days": 7,
            "hourly": ",".join(
                [
                    "temperature_2m",
                    "weather_code",
                    "precipitation_probability",
                    "wind_speed_10m",
                    "wind_gusts_10m",
                    "visibility",
                ]
            ),
        }
    )
    data = fetch_json(f"https://api.open-meteo.com/v1/forecast?{query}")
    hourly = data.get("hourly") or {}
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
        f"最低能见度{fmt(visibility_km, 'km', 1)}{note}"
    )


def build_report(text: str, message_timestamp: str) -> str:
    day = target_date(text, message_timestamp)
    locations = extract_locations(text)
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
