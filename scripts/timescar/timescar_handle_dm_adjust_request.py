#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from timescar_adjust_reservation_window import fetch_reservations, format_iso_minute, parse_iso_minute


TZ = ZoneInfo("Asia/Tokyo")
WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")
LEDGER_PATH = WORKSPACE / "var" / "timescar_dm_completed_requests.json"


class IntentError(RuntimeError):
    pass


def parse_message_time(raw: str) -> datetime:
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=TZ)
    return value.astimezone(TZ).replace(second=0, microsecond=0)


def normalize_text(text: str) -> str:
    return "".join(text.split())


def command_key(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def load_ledger() -> dict:
    if not LEDGER_PATH.exists():
        return {}
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def save_ledger(data: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(LEDGER_PATH)


def find_booking_for_start(reservations: list[dict], target_start: datetime) -> str | None:
    matches: list[dict] = []
    for reservation in reservations:
        try:
            start = parse_iso_minute(str(reservation.get("start") or ""))
        except Exception:
            continue
        if start == target_start:
            matches.append(reservation)
    if len(matches) != 1:
        return None
    return str(matches[0].get("bookingNumber") or "") or None


def interpret_adjust_request(text: str, message_time: datetime) -> tuple[datetime, datetime]:
    raw = text.strip()
    if not raw:
        raise IntentError("空指令")
    if "明天" not in raw or "后天" not in raw:
        raise IntentError("当前 TimesCar 专用执行器只接受明确包含“明天”和“后天”的改开始时间指令")
    if "开始" not in raw or ("订车" not in raw and "预约" not in raw and "TimesCar" not in raw and "timescar" not in raw):
        raise IntentError("不是明确的 TimesCar 预约开始时间变更指令")

    base_day = message_time.date()
    current_start = datetime.combine(base_day + timedelta(days=1), datetime.min.time(), tzinfo=TZ).replace(hour=9)
    new_start = datetime.combine(base_day + timedelta(days=2), datetime.min.time(), tzinfo=TZ).replace(hour=9)
    return current_start, new_start


def is_query_request(text: str) -> bool:
    raw = text.strip()
    if not any(token in raw for token in ("订车", "预约", "TimesCar", "timescar")):
        return False
    return any(token in raw for token in ("检查", "查询", "查看", "看看", "列表", "记录", "未来"))


def parse_query_hours(text: str) -> int:
    match = re.search(r"未来\s*(\d+)\s*(小时|小時|h|H)", text)
    if match:
        return max(1, min(int(match.group(1)), 24 * 30))
    match = re.search(r"未来\s*(\d+)\s*(天|日)", text)
    if match:
        return max(1, min(int(match.group(1)) * 24, 24 * 30))
    if "48" in text:
        return 48
    return 24


def format_query_result(text: str, message_time: datetime) -> str:
    hours = parse_query_hours(text)
    end_time = message_time + timedelta(hours=hours)
    reservations = []
    for reservation in fetch_reservations():
        try:
            start = parse_iso_minute(str(reservation.get("start") or ""))
            return_at = parse_iso_minute(str(reservation.get("return") or ""))
        except Exception:
            continue
        if message_time <= start <= end_time:
            reservations.append((start, return_at, reservation))
    reservations.sort(key=lambda item: item[0])
    header = [
        f"TimesCar 预约查询结果",
        f"范围：{format_iso_minute(message_time)} 至 {format_iso_minute(end_time)}（JST）",
    ]
    if not reservations:
        return "\n".join(header + ["状态：未来范围内没有即将开始的预约"])
    lines = header + [f"状态：找到 {len(reservations)} 单"]
    for index, (start, return_at, reservation) in enumerate(reservations, start=1):
        lines.extend(
            [
                "",
                f"{index}. 预约编号：{reservation.get('bookingNumber') or '未知'}",
                f"开始：{format_iso_minute(start)}",
                f"结束：{format_iso_minute(return_at)}",
                f"站点：{reservation.get('station') or reservation.get('place') or '未知'}",
                f"车辆：{reservation.get('carName') or reservation.get('vehicle') or '未知'}",
            ]
        )
    return "\n".join(lines)


def run_adjuster(booking: str, current_start: datetime, new_start: datetime, force: bool) -> subprocess.CompletedProcess[str]:
    cmd = [
        "python3",
        str(Path(__file__).with_name("timescar_adjust_reservation_window.py")),
        "--booking-number",
        booking,
        "--current-start",
        format_iso_minute(current_start),
        "--new-start",
        format_iso_minute(new_start),
        "--allow-already-applied",
    ]
    cmd.append("--force" if force else "--dry-run")
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--message-timestamp", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    message_time = parse_message_time(args.message_timestamp)
    if is_query_request(args.text):
        print(format_query_result(args.text, message_time))
        return 0

    current_start, new_start = interpret_adjust_request(args.text, message_time)
    key = command_key(args.text)
    ledger = load_ledger()
    previous = ledger.get(key)
    if previous and previous.get("status") == "ok":
        print(
            "\n".join(
                [
                    "TimesCar 预约变更结果",
                    "状态：该 Discord 私信指令此前已由汤猴完成，未重复提交",
                    f"上次完成：{previous.get('completedAt')}",
                    f"预约编号：{previous.get('bookingNumber')}",
                    f"目标开始：{previous.get('newStart')}",
                    f"目标结束：{previous.get('newReturn', '保持原结束时间')}",
                ]
            )
        )
        return 0

    reservations = fetch_reservations()
    booking = find_booking_for_start(reservations, current_start)
    if not booking:
        booking = find_booking_for_start(reservations, new_start)
    if not booking:
        raise IntentError(
            f"未能唯一定位 TimesCar 预约：currentStart={format_iso_minute(current_start)} "
            f"newStart={format_iso_minute(new_start)}"
        )

    result = run_adjuster(booking, current_start, new_start, args.force)
    print(result.stdout.strip())
    if result.returncode != 0:
        return result.returncode

    ledger[key] = {
        "status": "ok",
        "completedAt": datetime.now(TZ).isoformat(timespec="seconds"),
        "messageTime": message_time.isoformat(timespec="seconds"),
        "bookingNumber": booking,
        "currentStart": format_iso_minute(current_start),
        "newStart": format_iso_minute(new_start),
    }
    save_ledger(ledger)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"TimesCar 预约变更失败：{exc}")
        raise SystemExit(1)
