#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import sys

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from staged_jobs.task_trace import StagedTaskTrace

TZ = ZoneInfo("Asia/Tokyo")
STATE_DIR = Path("/var/lib/openclaw/.openclaw/workspace/state")
HOLIDAY_CACHE = STATE_DIR / "jp_holidays_cache.json"
HOLIDAY_URL = "https://holidays-jp.github.io/api/v1/date.json"


@dataclass(frozen=True)
class Location:
    label: str
    area: str
    latitude: float
    longitude: float


HOME_LOCATIONS = [
    Location("原人自宅", "杉並区", 35.6995, 139.6365),
    Location("熊自宅", "川口市", 35.8077, 139.7241),
]

OFFICE_LOCATION = Location("会社", "品川区", 35.6265, 139.7236)

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
    56: "小冻毛雨",
    57: "强冻毛雨",
    61: "小雨",
    63: "降雨",
    65: "大雨",
    66: "小冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "降雪",
    75: "大雪",
    77: "雪粒",
    80: "阵雨",
    81: "强阵雨",
    82: "暴雨阵雨",
    85: "阵雪",
    86: "强阵雪",
    95: "雷雨",
    96: "伴冰雹雷雨",
    99: "强烈雷雨",
}


def fetch_json(url: str, attempts: int = 3) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "OpenClawWeather/1.0",
            "Accept": "application/json",
        },
    )
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code < 500 or attempt >= attempts:
                raise
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = e
            if attempt >= attempts:
                raise
        time.sleep(min(2 * attempt, 6))
    if last_error:
        raise last_error
    raise RuntimeError("weather fetch failed without exception")


def load_holidays(target_year: int | None = None) -> dict[str, str]:
    """Load Japan public-holiday calendar used for red-day handling.

    The upstream JSON usually contains multiple years. Do not blindly trust an
    old cache when the requested year is absent; refresh it so future years are
    not accidentally treated as ordinary weekdays.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if HOLIDAY_CACHE.exists():
        try:
            data = json.loads(HOLIDAY_CACHE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                if target_year is None or any(str(k).startswith(f"{target_year}-") for k in data):
                    return data
        except Exception:
            pass
    data = fetch_json(HOLIDAY_URL)
    HOLIDAY_CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def holiday_name_for_date(day: datetime) -> str | None:
    key = day.strftime("%Y-%m-%d")
    try:
        holidays = load_holidays(day.year)
    except Exception:
        return None
    name = holidays.get(key)
    return str(name) if name else None


def is_rest_day(now: datetime) -> tuple[bool, str]:
    if now.weekday() >= 5:
        return True, "土日"
    holiday_name = holiday_name_for_date(now)
    if holiday_name:
        return True, f"祝日（{holiday_name}）"
    return False, "平日"


def locations_for_day(now: datetime) -> tuple[list[Location], bool, str]:
    rest_day, day_kind = is_rest_day(now)
    locations = list(HOME_LOCATIONS)
    # Japanese calendar red days are treated like weekends: no office forecast.
    if not rest_day:
        locations.append(OFFICE_LOCATION)
    return locations, rest_day, day_kind


def weather_label(code: int | None) -> str:
    if code is None:
        return "不明"
    return WEATHER_TEXT.get(code, f"天気コード{code}")


def traffic_advice(current_precip: float | None, max_precip_prob: float | None, wind: float | None, temp: float | None) -> str:
    precip_now = current_precip or 0.0
    precip_prob = max_precip_prob or 0.0
    wind_kmh = wind or 0.0
    temp_c = temp or 0.0
    if precip_now >= 0.5 or precip_prob >= 60:
        return "建议携带雨具，路面可能湿滑，出行时间尽量留出余量。"
    if wind_kmh >= 35:
        return "风力偏强，乘车和步行时要留意延误与横风影响。"
    if temp_c >= 28:
        return "气温偏高，注意防暑并优先补水。"
    if temp_c <= 3:
        return "早晨气温偏低，桥面和背阴处路面要多留意。"
    return "预计通勤和出行影响较小，可按常规安排。"


def format_number(value: float | int | None, suffix: str = "", digits: int = 0) -> str:
    if value is None:
        return "N/A"
    if digits == 0:
        return f"{int(round(float(value)))}{suffix}"
    return f"{float(value):.{digits}f}{suffix}"


def fetch_weather(location: Location) -> str:
    forecast_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
        {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "timezone": "Asia/Tokyo",
            "current": "temperature_2m,weather_code,precipitation,wind_speed_10m,uv_index",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "forecast_days": 2,
        }
    )
    air_url = "https://air-quality-api.open-meteo.com/v1/air-quality?" + urllib.parse.urlencode(
        {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "timezone": "Asia/Tokyo",
            "current": "us_aqi",
        }
    )

    try:
        forecast = fetch_json(forecast_url)
    except Exception as e:
        return f"- {location.label}（{location.area}）: 天气服务暂时不可用，无法取得实时预报（{type(e).__name__}）。"
    try:
        air = fetch_json(air_url)
    except Exception:
        air = {"current": {"us_aqi": None}}

    current = forecast.get("current", {})
    daily = forecast.get("daily", {})
    aqi = air.get("current", {}).get("us_aqi")

    temp = current.get("temperature_2m")
    code = current.get("weather_code")
    precip = current.get("precipitation")
    wind = current.get("wind_speed_10m")
    uv = current.get("uv_index")
    tmax = (daily.get("temperature_2m_max") or [None])[0]
    tmin = (daily.get("temperature_2m_min") or [None])[0]
    precip_prob = (daily.get("precipitation_probability_max") or [None])[0]

    advice = traffic_advice(precip, precip_prob, wind, temp)
    return (
        f"- {location.label}（{location.area}）: "
        f"{format_number(temp, '°C')} / {weather_label(code)} / "
        f"最高{format_number(tmax, '°C')} 最低{format_number(tmin, '°C')} / "
        f"UV {format_number(uv)} / AQI {format_number(aqi)} / "
        f"{advice}"
    )


def main() -> int:
    trace = StagedTaskTrace("weather-report-jst-0700", "weather")
    trace.start("decide-day-kind")
    now = datetime.now(TZ)
    locations, rest_day, day_kind = locations_for_day(now)
    trace.step("decide-day-kind", "ok", detail=f"{'rest-day' if rest_day else 'workday'} / {day_kind}", tool="calendar")

    lines = [f"天气预报 {now:%Y-%m-%d} {('休息日' if rest_day else '工作日')}（{day_kind}）"]
    for loc in locations:
        trace.step("fetch-weather", "running", detail=loc.label, tool="open-meteo")
        lines.append(fetch_weather(loc))
    message = "\n".join(lines)
    trace.artifact("locations", [loc.label for loc in locations])
    trace.finish("ok", "report-ready", final_message=message)
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
