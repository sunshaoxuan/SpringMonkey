#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
import re


UNIT_HOURS = {
    "小时": 1,
    "小時": 1,
    "時間": 1,
    "h": 1,
    "H": 1,
    "天": 24,
    "日": 24,
    "周": 24 * 7,
    "週": 24 * 7,
    "星期": 24 * 7,
    "礼拜": 24 * 7,
    "禮拜": 24 * 7,
    "週間": 24 * 7,
    "月": 24 * 30,
    "个月": 24 * 30,
    "個月": 24 * 30,
    "か月": 24 * 30,
    "ヶ月": 24 * 30,
}

CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "兩": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

JP_DIGITS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
RANGE_PATTERN = re.compile(
    r"(?:未来|今后|今後|接下来|接下來|向后|向後|之后|之後|后面|後面|next|for)?\s*"
    r"([0-9０-９]+|[零〇一二两兩三四五六七八九十百]+)\s*"
    r"(小时|小時|時間|h|H|天|日|周|週|星期|礼拜|禮拜|週間|个月|個月|か月|ヶ月|月)",
    re.IGNORECASE,
)
AFTER_SUFFIX_PATTERN = re.compile(r"(以后|以後|之后|之後|later)")


@dataclass(frozen=True)
class TimeRangeSpec:
    duration_hours: int
    offset_hours: int = 0
    relation: str = "within"


def parse_cjk_number(value: str) -> int | None:
    raw = (value or "").strip().translate(FULLWIDTH_DIGITS)
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    if raw in {"十"}:
        return 10
    if "百" in raw:
        parts = raw.split("百", 1)
        hundreds = parse_cjk_number(parts[0]) if parts[0] else 1
        rest = parse_cjk_number(parts[1]) if parts[1] else 0
        if hundreds is None or rest is None:
            return None
        return hundreds * 100 + rest
    if "十" in raw:
        parts = raw.split("十", 1)
        tens = parse_cjk_number(parts[0]) if parts[0] else 1
        ones = parse_cjk_number(parts[1]) if parts[1] else 0
        if tens is None or ones is None:
            return None
        return tens * 10 + ones
    total = 0
    for char in raw:
        if char not in CN_DIGITS and char not in JP_DIGITS:
            return None
        total = total * 10 + (CN_DIGITS.get(char) if char in CN_DIGITS else JP_DIGITS[char])
    return total


def requested_range_hours(text: str, *, default: int | None = None, max_hours: int = 24 * 30) -> int | None:
    spec = requested_range_spec(text, default=None, max_hours=max_hours)
    return spec.duration_hours if spec else default


def requested_range_spec(text: str, *, default: int | None = None, max_hours: int = 24 * 30) -> TimeRangeSpec | None:
    raw = text or ""
    for match in RANGE_PATTERN.finditer(raw):
        amount = parse_cjk_number(match.group(1))
        unit = match.group(2)
        if amount is None or amount <= 0:
            continue
        hours = amount * UNIT_HOURS[unit]
        duration = max(1, min(hours, max_hours))
        suffix = raw[match.end() : match.end() + 8]
        if AFTER_SUFFIX_PATTERN.search(suffix):
            return TimeRangeSpec(duration_hours=duration, offset_hours=duration, relation="after")
        return TimeRangeSpec(duration_hours=duration)
    if "48" in raw:
        duration = min(48, max_hours)
        return TimeRangeSpec(duration_hours=duration)
    if default is None:
        return None
    return TimeRangeSpec(duration_hours=default)
