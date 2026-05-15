#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
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

from nl_time_range import requested_range_hours, requested_range_spec
from model_fallback_client import chat_with_fallback

TZ = ZoneInfo("Asia/Tokyo")
WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")
LEDGER_PATH = WORKSPACE / "var" / "timescar_dm_completed_requests.json"
DECISIONS_PATH = WORKSPACE / ".secure" / "timescar_user_decisions.json"
CANCEL_LEDGER_PATH = WORKSPACE / "var" / "timescar_dm_cancelled_requests.json"


class IntentError(RuntimeError):
    pass


def extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise IntentError(f"模型未返回 JSON 契约：{raw[:160]}")
    data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise IntentError("模型返回的调整契约不是 JSON object")
    return data


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


def find_unique_reservation_start_on_date(reservations: list[dict], target_date) -> datetime | None:
    matches: list[datetime] = []
    for reservation in reservations:
        try:
            start = parse_iso_minute(str(reservation.get("start") or ""))
        except Exception:
            continue
        if start.date() == target_date:
            matches.append(start)
    unique = sorted(set(matches))
    if len(unique) != 1:
        return None
    return unique[0]


def reservation_contract_context(reservations: list[dict]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for reservation in reservations:
        items.append(
            {
                "bookingNumber": str(reservation.get("bookingNumber") or ""),
                "start": str(reservation.get("start") or ""),
                "return": str(reservation.get("return") or ""),
                "station": str(reservation.get("station") or reservation.get("place") or ""),
                "vehicle": str(reservation.get("vehicle") or reservation.get("carName") or ""),
            }
        )
    return items


def classify_adjust_contract(
    text: str,
    message_time: datetime,
    reservations: list[dict],
    *,
    model_caller: Callable[[list[dict[str, str]]], str] | None = None,
) -> dict[str, Any]:
    system = (
        "You are a semantic contract parser for a TimesCar owner-DM executor. "
        "Classify by meaning, not keyword matching. Return strict JSON only. "
        "Schema: {supported:boolean, operation:'adjust_start'|'shift_window'|'unsupported', "
        "target:{selector:'booking_number'|'relative_day_unique_reservation'|'next_within_hours', booking_number:string|null, relative_days:int|null, within_hours:int|null}, "
        "start_shift_minutes:int|null, new_start_local:string|null, preserve_return_time:boolean|null, shift_return_time:boolean|null, confidence:number, reason:string}. "
        "Use adjust_start when only the reservation start changes and return/end time is preserved. "
        "Use shift_window when start and return/end move together by the same duration. "
        "If the request is not a concrete TimesCar reservation time adjustment, set supported=false. "
        "For relative days, base them on message_time in Asia/Tokyo: tomorrow means relative_days=1. "
        "Use next_within_hours when the user refers to this/next/imminent reservation without a date."
    )
    user = json.dumps(
        {
            "message_time": message_time.isoformat(timespec="minutes"),
            "user_text": text,
            "current_reservations": reservation_contract_context(reservations),
        },
        ensure_ascii=False,
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if model_caller:
        content = model_caller(messages)
    else:
        content, _meta = chat_with_fallback(messages, timeout=30, temperature=0)
    contract = extract_json_object(content)
    if not bool(contract.get("supported")):
        raise IntentError(str(contract.get("reason") or "模型判断该指令不是受支持的 TimesCar 时间调整契约"))
    operation = str(contract.get("operation") or "")
    if operation not in {"adjust_start", "shift_window"}:
        raise IntentError(f"模型返回了不支持的 TimesCar 调整操作：{operation}")
    try:
        confidence = float(contract.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < 0.65:
        raise IntentError(f"TimesCar 调整契约置信度过低：{confidence}")
    return contract


def classify_timescar_operation_contract(
    text: str,
    message_time: datetime,
    reservations: list[dict],
    *,
    model_caller: Callable[[list[dict[str, str]]], str] | None = None,
) -> dict[str, Any]:
    system = (
        "You are a semantic operation-contract parser for a TimesCar owner-DM executor. "
        "Classify by meaning, not keyword matching. Return strict JSON only. "
        "Schema: {supported:boolean, operation:'query'|'book_window'|'keep_next'|'cancel_next'|'cancel_status'|'adjust_start'|'shift_window'|'unsupported', "
        "confidence:number, reason:string}. "
        "Use query for read-only reservation list/range checks. "
        "Use book_window for creating a reservation. Use keep_next for recording a keep decision. "
        "Use cancel_next for cancelling a reservation. Use cancel_status for checking whether cancellation succeeded. "
        "Use adjust_start when only reservation start changes and return/end is preserved. "
        "Use shift_window when start and return/end move together by the same duration. "
        "If not a concrete TimesCar reservation operation, supported=false."
    )
    user = json.dumps(
        {
            "message_time": message_time.isoformat(timespec="minutes"),
            "user_text": text,
            "current_reservations": reservation_contract_context(reservations),
        },
        ensure_ascii=False,
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if model_caller:
        content = model_caller(messages)
    else:
        content, _meta = chat_with_fallback(messages, timeout=30, temperature=0)
    contract = extract_json_object(content)
    if not bool(contract.get("supported")):
        raise IntentError(str(contract.get("reason") or "模型判断该指令不是受支持的 TimesCar 操作契约"))
    operation = str(contract.get("operation") or "")
    allowed = {"query", "book_window", "keep_next", "cancel_next", "cancel_status", "adjust_start", "shift_window"}
    if operation not in allowed:
        raise IntentError(f"模型返回了不支持的 TimesCar 操作：{operation}")
    try:
        confidence = float(contract.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < 0.65:
        raise IntentError(f"TimesCar 操作契约置信度过低：{confidence}")
    return contract


def operation_from_tool_id(tool_id: str) -> str | None:
    return {
        "timescar.dm.query": "query",
        "timescar.dm.book_window": "book_window",
        "timescar.dm.keep_next": "keep_next",
        "timescar.dm.cancel_next": "cancel_next",
        "timescar.dm.cancel_status": "cancel_status",
        "timescar.dm.adjust_start": "adjust_start",
        "timescar.dm.shift_window": "shift_window",
    }.get(str(tool_id or ""))


def resolve_timescar_operation(text: str, message_time: datetime, tool_id: str = "") -> str:
    operation = operation_from_tool_id(tool_id)
    if operation:
        return operation
    contract = classify_timescar_operation_contract(text, message_time, fetch_reservations())
    return str(contract["operation"])


def classify_book_contract(
    text: str,
    message_time: datetime,
    *,
    model_caller: Callable[[list[dict[str, str]]], str] | None = None,
) -> dict[str, Any]:
    system = (
        "You are a semantic contract parser for a TimesCar booking executor. "
        "Classify by meaning, not keyword matching. Return strict JSON only. "
        "Schema: {supported:boolean, start_local:string|null, end_local:string|null, model_preference:string, confidence:number, reason:string}. "
        "start_local and end_local must be local Asia/Tokyo timestamps formatted YYYY-MM-DDTHH:MM. "
        "model_preference should be the requested vehicle/model preference, or 'any' when the user asks to use any available car. "
        "If the request is not a concrete TimesCar booking request, supported=false."
    )
    user = json.dumps({"message_time": message_time.isoformat(timespec="minutes"), "user_text": text}, ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if model_caller:
        content = model_caller(messages)
    else:
        content, _meta = chat_with_fallback(messages, timeout=30, temperature=0)
    contract = extract_json_object(content)
    if not bool(contract.get("supported")):
        raise IntentError(str(contract.get("reason") or "模型判断该指令不是受支持的 TimesCar 预订契约"))
    try:
        confidence = float(contract.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < 0.65:
        raise IntentError(f"TimesCar 预订契约置信度过低：{confidence}")
    if not contract.get("start_local") or not contract.get("end_local"):
        raise IntentError("TimesCar 预订契约缺少 start_local/end_local")
    if not str(contract.get("model_preference") or "").strip():
        contract["model_preference"] = "ヤリスクロス（ハイブリッド）"
    return contract


def reservation_by_contract_target(reservations: list[dict], target: dict[str, Any], message_time: datetime) -> dict:
    selector = str(target.get("selector") or "")
    if selector == "booking_number":
        booking = str(target.get("booking_number") or "")
        matches = [item for item in reservations if str(item.get("bookingNumber") or "") == booking]
    elif selector == "relative_day_unique_reservation":
        relative_days = int(target.get("relative_days") or 0)
        wanted_date = (message_time + timedelta(days=relative_days)).date()
        matches = []
        for item in reservations:
            try:
                if parse_iso_minute(str(item.get("start") or "")).date() == wanted_date:
                    matches.append(item)
            except Exception:
                continue
    elif selector == "next_within_hours":
        hours = int(target.get("within_hours") or 48)
        next_reservation = find_next_reservation(reservations, message_time, hours=hours)
        matches = [next_reservation] if next_reservation else []
    else:
        raise IntentError(f"模型返回了不支持的目标选择器：{selector}")
    if len(matches) != 1 or matches[0] is None:
        raise IntentError(f"未能按语义契约唯一定位 TimesCar 预约：selector={selector}")
    return matches[0]


def parse_contract_new_start(contract: dict[str, Any], current_start: datetime) -> datetime:
    raw_new_start = str(contract.get("new_start_local") or "").strip()
    if raw_new_start:
        return parse_iso_minute(raw_new_start)
    shift_raw = contract.get("start_shift_minutes")
    if shift_raw is None:
        raise IntentError("调整契约缺少 new_start_local 或 start_shift_minutes")
    return current_start + timedelta(minutes=int(shift_raw))


def interpret_adjust_contract(
    text: str,
    message_time: datetime,
    *,
    model_caller: Callable[[list[dict[str, str]]], str] | None = None,
) -> tuple[str, datetime, datetime, datetime | None]:
    reservations = fetch_reservations()
    contract = classify_adjust_contract(text, message_time, reservations, model_caller=model_caller)
    target = contract.get("target") if isinstance(contract.get("target"), dict) else {}
    reservation = reservation_by_contract_target(reservations, target, message_time)
    booking = str(reservation.get("bookingNumber") or "")
    if not booking:
        raise IntentError("语义契约定位到预约但缺少预约编号")
    current_start = parse_iso_minute(str(reservation.get("start") or ""))
    current_return = parse_iso_minute(str(reservation.get("return") or ""))
    new_start = parse_contract_new_start(contract, current_start)
    operation = str(contract.get("operation") or "")
    preserve_return = bool(contract.get("preserve_return_time"))
    shift_return = bool(contract.get("shift_return_time"))
    if operation == "adjust_start":
        if not preserve_return or shift_return:
            raise IntentError("adjust_start 契约必须保持结束时间不变")
        return booking, current_start, new_start, None
    if operation == "shift_window":
        if preserve_return or not shift_return:
            raise IntentError("shift_window 契约必须同时平移结束时间")
        delta = new_start - current_start
        return booking, current_start, new_start, current_return + delta
    raise IntentError(f"不支持的调整契约操作：{operation}")


def parse_query_hours(text: str) -> int:
    return int(requested_range_hours(text, default=24) or 24)


def parse_query_window(text: str) -> tuple[int, int]:
    spec = requested_range_spec(text, default=24)
    if spec is None:
        return 0, 24
    return spec.offset_hours, spec.duration_hours


def format_query_result(text: str, message_time: datetime) -> str:
    offset_hours, hours = parse_query_window(text)
    start_time = message_time + timedelta(hours=offset_hours)
    end_time = start_time + timedelta(hours=hours)
    reservations = []
    for reservation in fetch_reservations():
        try:
            start = parse_iso_minute(str(reservation.get("start") or ""))
            return_at = parse_iso_minute(str(reservation.get("return") or ""))
        except Exception:
            continue
        if start_time <= start <= end_time:
            reservations.append((start, return_at, reservation))
    reservations.sort(key=lambda item: item[0])
    header = [
        f"TimesCar 预约查询结果",
        f"范围：{format_iso_minute(start_time)} 至 {format_iso_minute(end_time)}（JST）",
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
    contract = classify_book_contract(text, message_time)
    start = parse_iso_minute(str(contract["start_local"]))
    end = parse_iso_minute(str(contract["end_local"]))
    if start >= end:
        raise IntentError("TimesCar 预订契约的开始时间必须早于结束时间")
    result = run_booker(start, end, force, str(contract.get("model_preference") or "ヤリスクロス（ハイブリッド）"))
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


def run_adjuster(
    booking: str,
    current_start: datetime,
    new_start: datetime,
    force: bool,
    new_return: datetime | None = None,
) -> subprocess.CompletedProcess[str]:
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
    if new_return is not None:
        cmd.extend(["--new-return", format_iso_minute(new_return)])
    cmd.append("--force" if force else "--dry-run")
    return run_child_tool(cmd)


def format_shift_window_result(text: str, message_time: datetime, force: bool) -> str:
    booking, current_start, new_start, new_return = interpret_adjust_contract(text, message_time)
    if new_return is None:
        raise IntentError("语义契约不是整体平移窗口")
    key = "shift_window:" + command_key(text)
    ledger = load_ledger()
    previous = ledger.get(key)
    if previous and previous.get("status") == "ok":
        return "\n".join(
            [
                "TimesCar 预约整体平移结果",
                "状态：该 Discord 私信指令此前已由汤猴完成，未重复提交",
                f"上次完成：{previous.get('completedAt')}",
                f"预约编号：{previous.get('bookingNumber')}",
                f"目标开始：{previous.get('newStart')}",
                f"目标结束：{previous.get('newReturn')}",
            ]
        )

    result = run_adjuster(booking, current_start, new_start, force, new_return=new_return)
    output = result.stdout.strip()
    if result.returncode != 0:
        raise IntentError(output or f"TimesCar 整体平移执行器失败，退出码：{result.returncode}")

    ledger[key] = {
        "status": "ok",
        "completedAt": datetime.now(TZ).isoformat(timespec="seconds"),
        "messageTime": message_time.isoformat(timespec="seconds"),
        "bookingNumber": booking,
        "currentStart": format_iso_minute(current_start),
        "newStart": format_iso_minute(new_start),
        "newReturn": format_iso_minute(new_return),
    }
    save_ledger(ledger)
    return output


def format_adjust_result(text: str, message_time: datetime, force: bool) -> str:
    booking, current_start, new_start, new_return = interpret_adjust_contract(text, message_time)
    if new_return is not None:
        return format_shift_window_result(text, message_time, force)
    key = command_key(text)
    ledger = load_ledger()
    previous = ledger.get(key)
    if previous and previous.get("status") == "ok":
        return "\n".join(
            [
                "TimesCar 预约变更结果",
                "状态：该 Discord 私信指令此前已由汤猴完成，未重复提交",
                f"上次完成：{previous.get('completedAt')}",
                f"预约编号：{previous.get('bookingNumber')}",
                f"目标开始：{previous.get('newStart')}",
                f"目标结束：{previous.get('newReturn', '保持原结束时间')}",
            ]
        )

    result = run_adjuster(booking, current_start, new_start, force)
    output = result.stdout.strip()
    if result.returncode != 0:
        raise IntentError(output or f"TimesCar 变更执行器失败，退出码：{result.returncode}")

    ledger[key] = {
        "status": "ok",
        "completedAt": datetime.now(TZ).isoformat(timespec="seconds"),
        "messageTime": message_time.isoformat(timespec="seconds"),
        "bookingNumber": booking,
        "currentStart": format_iso_minute(current_start),
        "newStart": format_iso_minute(new_start),
    }
    save_ledger(ledger)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--message-timestamp", required=True)
    parser.add_argument("--tool-id", default=os.environ.get("OPENCLAW_BOUND_TOOL_ID", ""))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    message_time = parse_message_time(args.message_timestamp)
    operation = resolve_timescar_operation(args.text, message_time, args.tool_id)
    if operation == "book_window":
        print(format_book_result(args.text, message_time, args.force))
        return 0
    if operation == "cancel_status":
        print(format_cancel_status_result(args.text, message_time))
        return 0
    if operation == "query":
        print(format_query_result(args.text, message_time))
        return 0
    if operation == "keep_next":
        print(format_keep_result(args.text, message_time))
        return 0
    if operation == "cancel_next":
        print(format_cancel_result(args.text, message_time, args.force))
        return 0
    if operation == "shift_window":
        print(format_shift_window_result(args.text, message_time, args.force))
        return 0
    if operation == "adjust_start":
        print(format_adjust_result(args.text, message_time, args.force))
        return 0
    raise IntentError(f"未能解析 TimesCar 操作契约：{operation}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"TimesCar 预约变更失败：{exc}")
        raise SystemExit(1)
