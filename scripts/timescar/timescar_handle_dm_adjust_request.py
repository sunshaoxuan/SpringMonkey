#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from timescar_adjust_reservation_window import fetch_reservations, format_iso_minute, parse_iso_minute

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

_OPENCLAW_DIR = Path(__file__).resolve().parents[1] / "openclaw"
if str(_OPENCLAW_DIR) not in sys.path:
    sys.path.insert(0, str(_OPENCLAW_DIR))

from nl_time_range import requested_range_hours

TZ = ZoneInfo("Asia/Tokyo")
WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")
LEDGER_PATH = WORKSPACE / "var" / "timescar_dm_completed_requests.json"
DECISIONS_PATH = WORKSPACE / ".secure" / "timescar_user_decisions.json"
CANCEL_LEDGER_PATH = WORKSPACE / "var" / "timescar_dm_cancelled_requests.json"


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


def load_decisions() -> dict:
    if not DECISIONS_PATH.exists():
        return {}
    try:
        return json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_decisions(data: dict) -> None:
    DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DECISIONS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(DECISIONS_PATH)


def load_cancel_ledger() -> dict:
    if not CANCEL_LEDGER_PATH.exists():
        return {}
    try:
        return json.loads(CANCEL_LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cancel_ledger(data: dict) -> None:
    CANCEL_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CANCEL_LEDGER_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(CANCEL_LEDGER_PATH)


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


def is_book_request(text: str) -> bool:
    raw = text.strip()
    if any(token in raw for token in ("取消", "保留", "查询", "查看", "检查", "状态", "改到", "改成", "变更", "开始时间", "后天", "延期", "延迟")):
        return False
    if any(token in raw for token in ("可以预订的车", "可预订的车", "能预订的车", "换车", "换成")) and any(
        token in raw for token in ("车", "车辆", "车型", "预订", "预约")
    ):
        return True
    if not any(token in raw for token in ("预订", "預訂", "预约", "訂車", "订车", "一单", "一臺", "一台", "车辆", "车型", "TimesCar", "timescar")):
        return False
    return any(token in raw for token in ("预订", "預訂", "预约一单", "订一单", "再预订", "明天")) and any(
        token in raw for token in ("9点", "九点", "09", "早9", "早上9", "21点", "到21", "惯用", "车型")
    )


def is_cancel_status_request(text: str) -> bool:
    raw = text.strip()
    if not any(token in raw for token in ("订车", "预约", "这单", "订单", "TimesCar", "timescar", "取消")):
        return False
    return any(token in raw for token in ("取消了吗", "取消了么", "取消成功", "是否取消", "有没有取消", "还在吗", "还在不在", "状态"))


def is_keep_request(text: str) -> bool:
    raw = text.strip()
    if not any(token in raw for token in ("订车", "预约", "这单", "订单", "TimesCar", "timescar")):
        return False
    return any(token in raw for token in ("保留", "不要取消", "不取消", "keep"))


def is_cancel_request(text: str) -> bool:
    raw = text.strip()
    if not any(token in raw for token in ("订车", "预约", "这单", "刚刚这单", "刚才这单", "订单", "TimesCar", "timescar")):
        return False
    if "取消明天的时间" in raw and "后天" in raw:
        return False
    return any(token in raw for token in ("取消这单", "这单取消", "把这单取消", "刚刚这单取消", "刚才这单取消", "取消掉", "取消订单", "取消预约", "取消订车", "cancel"))


def is_adjust_request(text: str) -> bool:
    raw = text.strip()
    if is_cancel_request(raw) or is_keep_request(raw) or is_book_request(raw) or is_cancel_status_request(raw) or is_query_request(raw):
        return False
    if not any(token in raw for token in ("订车", "预约", "TimesCar", "timescar")):
        return False
    if not any(token in raw for token in ("开始时间", "后天", "延迟", "延期", "变更", "改到", "改成", "结束时间不变")):
        return False
    return any(token in raw for token in ("后天", "开始时间", "早上9点", "早9点", "09", "结束时间不变"))


def parse_query_hours(text: str) -> int:
    return int(requested_range_hours(text, default=24) or 24)


def interpret_book_request(text: str, message_time: datetime) -> tuple[datetime, datetime]:
    raw = text.strip()
    any_available_followup = any(token in raw for token in ("可以预订的车", "可预订的车", "能预订的车", "换车", "换成"))
    if "明天" not in raw and not any_available_followup:
        raise IntentError("当前 TimesCar 预订执行器只接受明确包含“明天”的预订指令")
    if not any_available_followup and not any(token in raw for token in ("9点", "九点", "09", "早9", "早上9")):
        raise IntentError("当前 TimesCar 预订执行器需要明确开始时间为 09:00")
    if not any_available_followup and not any(token in raw for token in ("21点", "二十一点", "到21", "至21")):
        raise IntentError("当前 TimesCar 预订执行器需要明确结束时间为 21:00")
    base_day = message_time.astimezone(TZ).date()
    start = datetime.combine(base_day + timedelta(days=1), datetime.min.time(), tzinfo=TZ).replace(hour=9)
    end = start.replace(hour=21)
    return start, end


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


def find_next_reservation(reservations: list[dict], message_time: datetime, hours: int = 48) -> dict | None:
    deadline = message_time + timedelta(hours=hours)
    candidates = []
    for reservation in reservations:
        try:
            start = parse_iso_minute(str(reservation.get("start") or ""))
        except Exception:
            continue
        if message_time <= start <= deadline:
            candidates.append((start, reservation))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[0][1]


def format_keep_result(text: str, message_time: datetime) -> str:
    reservation = find_next_reservation(fetch_reservations(), message_time)
    if reservation is None:
        return "\n".join(
            [
                "TimesCar 预约保留结果",
                "状态：未来 48 小时内没有找到可保留的预约，未写入保留决定",
            ]
        )
    booking = str(reservation.get("bookingNumber") or "")
    if not booking:
        raise IntentError("找到预约但缺少预约编号，无法写入保留决定")
    start = parse_iso_minute(str(reservation.get("start") or ""))
    expires_at = start + timedelta(hours=6)
    data = load_decisions()
    keep_map = data.setdefault("keepBookingNumbers", {})
    keep_map[booking] = {
        "status": "keep",
        "decidedAt": datetime.now(TZ).isoformat(timespec="seconds"),
        "expiresAt": expires_at.isoformat(timespec="seconds"),
        "source": "discord_dm",
        "textHash": command_key(text),
        "start": format_iso_minute(start),
    }
    save_decisions(data)
    return "\n".join(
        [
            "TimesCar 预约保留结果",
            "状态：已记录保留决定，后续 24 小时取消提醒会跳过该预约",
            f"预约编号：{booking}",
            f"开始：{format_iso_minute(start)}",
            f"保留记录有效至：{expires_at.isoformat(timespec='minutes')}",
        ]
    )


def run_child_tool(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1800)
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result


def run_canceller(booking: str, current_start: datetime, force: bool) -> subprocess.CompletedProcess[str]:
    cmd = [
        "python3",
        str(Path(__file__).with_name("timescar_cancel_reservation.py")),
        "--booking-number",
        booking,
        "--current-start",
        format_iso_minute(current_start),
        "--allow-already-cancelled",
    ]
    cmd.append("--force" if force else "--dry-run")
    return run_child_tool(cmd)


def book_model_preference(text: str) -> str:
    raw = text.strip()
    if any(token in raw for token in ("可以预订的车", "可预订的车", "能预订的车", "换车", "换成")):
        return "any"
    return "ヤリスクロス（ハイブリッド）"


def run_booker(start: datetime, end: datetime, force: bool, model_preference: str) -> subprocess.CompletedProcess[str]:
    cmd = [
        "python3",
        str(Path(__file__).with_name("timescar_book_reservation_window.py")),
        "--start",
        format_iso_minute(start),
        "--end",
        format_iso_minute(end),
        "--station-code",
        "JV56",
        "--model-preference",
        model_preference,
    ]
    cmd.append("--force" if force else "--dry-run")
    return run_child_tool(cmd)


def format_book_result(text: str, message_time: datetime, force: bool) -> str:
    start, end = interpret_book_request(text, message_time)
    result = run_booker(start, end, force, book_model_preference(text))
    output = result.stdout.strip()
    if result.returncode != 0:
        raise IntentError(output or f"TimesCar 预订执行器失败，退出码：{result.returncode}")
    return output


def format_cancel_result(text: str, message_time: datetime, force: bool) -> str:
    reservation = find_next_reservation(fetch_reservations(), message_time)
    if reservation is None:
        return "\n".join(
            [
                "TimesCar 取消预约结果",
                "状态：未来 48 小时内没有找到可取消的预约，未执行取消",
            ]
        )
    booking = str(reservation.get("bookingNumber") or "")
    if not booking:
        raise IntentError("找到预约但缺少预约编号，无法执行取消")
    start = parse_iso_minute(str(reservation.get("start") or ""))
    result = run_canceller(booking, start, force)
    output = result.stdout.strip()
    if result.returncode != 0:
        raise IntentError(output or f"TimesCar 取消执行器失败，退出码：{result.returncode}")
    if force:
        data = load_cancel_ledger()
        cancels = data.setdefault("cancelledBookingNumbers", {})
        cancels[booking] = {
            "status": "cancelled",
            "completedAt": datetime.now(TZ).isoformat(timespec="seconds"),
            "source": "discord_dm",
            "textHash": command_key(text),
            "start": format_iso_minute(start),
            "rawOutput": output[-2000:],
        }
        save_cancel_ledger(data)
    return output


def extract_booking_number(text: str) -> str | None:
    match = re.search(r"\b(\d{6,12})\b", text)
    return match.group(1) if match else None


def latest_cancel_record(data: dict) -> tuple[str, dict] | None:
    records = data.get("cancelledBookingNumbers") or {}
    if not isinstance(records, dict) or not records:
        return None
    items = [(str(booking), record) for booking, record in records.items() if isinstance(record, dict)]
    if not items:
        return None
    return sorted(items, key=lambda item: str(item[1].get("completedAt") or ""), reverse=True)[0]


def format_cancel_status_result(text: str, message_time: datetime) -> str:
    reservations = fetch_reservations()
    booking = extract_booking_number(text)
    data = load_cancel_ledger()
    record: dict | None = None
    if booking:
        record = (data.get("cancelledBookingNumbers") or {}).get(booking)
    else:
        latest = latest_cancel_record(data)
        if latest:
            booking, record = latest

    if booking:
        active = [item for item in reservations if str(item.get("bookingNumber") or "") == booking]
        if active:
            reservation = active[0]
            return "\n".join(
                [
                    "TimesCar 取消状态确认",
                    "状态：该预约仍在当前预约列表中，未确认取消成功",
                    f"预约编号：{booking}",
                    f"开始：{reservation.get('start') or '未知'}",
                    f"结束：{reservation.get('return') or '未知'}",
                ]
            )
        if record:
            return "\n".join(
                [
                    "TimesCar 取消状态确认",
                    "状态：已取消，当前预约列表中已不存在该预约",
                    f"预约编号：{booking}",
                    f"取消完成：{record.get('completedAt') or '未知'}",
                    f"原开始：{record.get('start') or '未知'}",
                ]
            )
        return "\n".join(
            [
                "TimesCar 取消状态确认",
                "状态：当前预约列表中不存在该预约，但本地没有找到汤猴取消成功记录",
                f"预约编号：{booking}",
                "说明：可能已取消，或不是由汤猴最近一次取消流程完成。",
            ]
        )

    next_reservation = find_next_reservation(reservations, message_time)
    if next_reservation is None:
        return "\n".join(
            [
                "TimesCar 取消状态确认",
                "状态：未来 48 小时内没有即将开始的 TimesCar 预约",
                "说明：如果你问的是刚才那单，它当前已不在预约列表中。",
            ]
        )
    return "\n".join(
        [
            "TimesCar 取消状态确认",
            "状态：仍存在即将开始的 TimesCar 预约",
            f"预约编号：{next_reservation.get('bookingNumber') or '未知'}",
            f"开始：{next_reservation.get('start') or '未知'}",
            f"结束：{next_reservation.get('return') or '未知'}",
        ]
    )


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
    return run_child_tool(cmd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--message-timestamp", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    message_time = parse_message_time(args.message_timestamp)
    if is_book_request(args.text):
        print(format_book_result(args.text, message_time, args.force))
        return 0
    if is_cancel_status_request(args.text):
        print(format_cancel_status_result(args.text, message_time))
        return 0
    if is_query_request(args.text):
        print(format_query_result(args.text, message_time))
        return 0
    if is_keep_request(args.text):
        print(format_keep_result(args.text, message_time))
        return 0
    if is_cancel_request(args.text):
        print(format_cancel_result(args.text, message_time, args.force))
        return 0

    if not is_adjust_request(args.text):
        raise IntentError("未能识别 TimesCar 子意图，未执行任何预约变更")

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
