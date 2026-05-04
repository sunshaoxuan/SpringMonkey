#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from task_runtime import TimesCarTaskRuntime

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")
SECRET_CMD = ["bash", str(WORKSPACE / "scripts" / "timescar_secret.sh")]
TZ = ZoneInfo("Asia/Tokyo")
DEFAULT_STATION_CODE = "JV56"
DEFAULT_STATION_NAME = "久我山４丁目２"
DEFAULT_MODEL_PREFERENCE = "ヤリスクロス（ハイブリッド）"
DEFAULT_MODEL_FALLBACK = "ヤリスクロス"
PREFERRED_IDENT = "1286"
PREFERRED_COLOR = "グレイッシュブルー"
JOB_NAME = "timescar-book-reservation-window"


class BookingWindowError(RuntimeError):
    pass


def extract_json(raw: str) -> dict:
    raw = raw.strip()
    if not raw:
        raise ValueError("empty output")
    try:
        return json.loads(raw)
    except Exception:
        pass
    match = re.search(r"(\{[\s\S]*\})\s*$", raw)
    if not match:
        raise ValueError(f"no trailing json object found in: {raw[:200]}...")
    return json.loads(match.group(1))


def run_json(cmd: list[str]) -> dict:
    return extract_json(subprocess.check_output(cmd, text=True))


def load_credentials() -> tuple[str, str, str]:
    data = run_json(SECRET_CMD)
    p1, p2 = data["member_number_parts"]
    return p1, p2, data["password"]


def fetch_reservations() -> list[dict]:
    data = json.loads(subprocess.check_output(["python3", str(Path(__file__).with_name("timescar_fetch_reservations.py"))], text=True))
    return data.get("reservations", [])


def parse_iso_minute(raw: str) -> datetime:
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None:
        value = value.replace(tzinfo=TZ)
    return value.astimezone(TZ).replace(second=0, microsecond=0)


def format_iso_minute(value: datetime) -> str:
    return value.astimezone(TZ).strftime("%Y-%m-%dT%H:%M")


def reserve_input_url(station_code: str) -> str:
    return f"https://share.timescar.jp/view/reserve/input.jsp?scd={station_code}"


def is_login(page) -> bool:
    return bool(page.locator("#cardNo1").count() and page.locator("#tpPassword").count())


def login_if_needed(page, p1: str, p2: str, password: str) -> None:
    if not is_login(page):
        return
    page.fill("#cardNo1", p1)
    page.fill("#cardNo2", p2)
    page.fill("#tpPassword", password)
    page.locator("#doLoginForTp").click()
    page.wait_for_url("**/view/member/mypage.jsp", timeout=45000)


def option_texts(page, selector: str) -> list[dict[str, str]]:
    return page.locator(f"{selector} option").evaluate_all(
        "els => els.map(o => ({text:(o.textContent||'').trim(), value:o.value}))"
    )


def find_model_value(page, model_preference: str) -> str:
    options = option_texts(page, "#carId")
    for wanted in (model_preference, DEFAULT_MODEL_FALLBACK):
        for item in options:
            if wanted and wanted in item["text"]:
                return item["value"]
    raise BookingWindowError(f"failed: station has no preferred model: {model_preference}")


def same_window(reservation: dict, start: datetime, end: datetime, station_name: str, model_preference: str) -> bool:
    try:
        reservation_start = parse_iso_minute(str(reservation.get("start") or ""))
        reservation_end = parse_iso_minute(str(reservation.get("return") or ""))
    except Exception:
        return False
    vehicle = str(reservation.get("vehicle") or reservation.get("carName") or "")
    return (
        reservation_start == start
        and reservation_end == end
        and str(reservation.get("station") or "") == station_name
        and (DEFAULT_MODEL_FALLBACK in vehicle or model_preference in vehicle)
    )


def existing_reservation_for_window(start: datetime, end: datetime, station_name: str, model_preference: str) -> dict | None:
    matches = [item for item in fetch_reservations() if same_window(item, start, end, station_name, model_preference)]
    if not matches:
        return None
    matches.sort(key=lambda item: str(item.get("acceptedAt") or ""))
    return matches[-1]


def keep_same_car(reservation: dict) -> str:
    return "是" if PREFERRED_IDENT in str(reservation.get("carIdentifier") or "") and reservation.get("carColor") == PREFERRED_COLOR else "否"


def format_report(reservation: dict, dry_run: bool = False) -> str:
    status = "dry-run 校验成功，未提交预订" if dry_run else "预约已提交并回查确认"
    return "\n".join(
        [
            "TimesCar 预订结果",
            f"状态：{status}",
            f"预约编号：{reservation.get('bookingNumber', 'dry-run')}",
            f"预约开始：{reservation.get('startText') or reservation.get('start') or ''}",
            f"返却予定：{reservation.get('returnText') or reservation.get('return') or ''}",
            f"ステーション：{reservation.get('station') or DEFAULT_STATION_NAME}",
            f"车辆：{reservation.get('vehicle') or DEFAULT_MODEL_FALLBACK}",
            f"车牌/识别：{reservation.get('carIdentifier', '')}",
            f"车身颜色：{reservation.get('carColor', '')}",
            f"是否保留同车：{keep_same_car(reservation)}",
        ]
    )


def assert_confirm_page(body: str, start: datetime, end: datetime, station_name: str, model_preference: str) -> None:
    if "入力内容に誤りがあります" in body:
        raise BookingWindowError("failed: booking form validation error")
    if "予約登録（確認）" not in body and "予約登録(確認)" not in body:
        raise BookingWindowError("failed: did not reach booking confirm page")
    start_pattern = rf"利用開始日時\s*{start.year:04d}年{start.month:02d}月{start.day:02d}日（[^）]+）{start.hour:02d}:{start.minute:02d}"
    end_pattern = rf"返却予定日時\s*{end.year:04d}年{end.month:02d}月{end.day:02d}日（[^）]+）{end.hour:02d}:{end.minute:02d}"
    if not re.search(start_pattern, body):
        raise BookingWindowError("failed: confirm page start time mismatch")
    if not re.search(end_pattern, body):
        raise BookingWindowError("failed: confirm page return time mismatch")
    if station_name not in body:
        raise BookingWindowError("failed: confirm page station mismatch")
    if model_preference not in body and DEFAULT_MODEL_FALLBACK not in body:
        raise BookingWindowError("failed: confirm page model mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="YYYY-MM-DDTHH:MM in JST")
    parser.add_argument("--end", required=True, help="YYYY-MM-DDTHH:MM in JST")
    parser.add_argument("--station-code", default=DEFAULT_STATION_CODE)
    parser.add_argument("--station-name", default=DEFAULT_STATION_NAME)
    parser.add_argument("--model-preference", default=DEFAULT_MODEL_PREFERENCE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.dry_run and args.force:
        raise SystemExit("--dry-run and --force are mutually exclusive")

    runtime = TimesCarTaskRuntime(JOB_NAME, "write", ttl_seconds=1800)
    phase = "init"
    try:
        runtime.start("load-credentials")
        start = parse_iso_minute(args.start)
        end = parse_iso_minute(args.end)
        if start >= end:
            raise BookingWindowError("failed: start must be earlier than end")
        existing = existing_reservation_for_window(start, end, args.station_name, args.model_preference)
        runtime.record_step(step="check-existing-reservation", status="ok", tool="timescar_fetch_reservations.py", detail="checked target window")
        if existing:
            message = "已存在目标窗口预约，无需重复预订。\n" + format_report(existing)
            runtime.finish("skipped", "already-booked", final_message=message)
            print(message)
            return 0

        p1, p2, password = load_credentials()
        runtime.record_step(step="load-credentials", status="ok", tool="secret.sh", detail="loaded TimesCar credentials")
        url = reserve_input_url(args.station_code)
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:18800")
            ctx = browser.contexts[0]
            page = ctx.new_page()
            page.set_default_timeout(45000)
            phase = "open-booking-page"
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            login_if_needed(page, p1, p2, password)
            if page.url != url:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            runtime.record_step(step=phase, status="ok", tool="browser", detail="opened reservation input page")

            model_value = find_model_value(page, args.model_preference)
            page.select_option("#carId", model_value)
            page.select_option("#dateStart", start.strftime("%Y-%m-%d 00:00:00.0"))
            page.select_option("#hourStart", str(start.hour))
            page.select_option("#minuteStart", f"{start.minute:02d}")
            page.select_option("#dateEnd", end.strftime("%Y-%m-%d 00:00:00.0"))
            page.select_option("#hourEnd", str(end.hour))
            page.select_option("#minuteEnd", f"{end.minute:02d}")
            if page.locator("#exemptNocFlgYes").count():
                page.check("#exemptNocFlgYes")

            phase = "validate-booking-form"
            page.locator("#doCheck").click()
            page.wait_for_load_state("domcontentloaded")
            body = page.locator("body").inner_text()
            assert_confirm_page(body, start, end, args.station_name, args.model_preference)
            runtime.record_step(step=phase, status="ok", tool="browser", detail="reached and verified booking confirm page")

            if args.dry_run or not args.force:
                dry_run_payload = {
                    "bookingNumber": "dry-run",
                    "start": format_iso_minute(start),
                    "return": format_iso_minute(end),
                    "station": args.station_name,
                    "vehicle": args.model_preference,
                    "carIdentifier": "",
                    "carColor": "",
                }
                message = format_report(dry_run_payload, dry_run=True)
                runtime.finish("ok", "dry-run", final_message=message)
                print(message)
                return 0

            phase = "submit-booking"
            page.locator("#doOnceRegist").click()
            page.wait_for_load_state("domcontentloaded")
            done_text = page.locator("body").inner_text()
            if "予約登録を受付けました。" not in done_text:
                raise BookingWindowError("failed: reservation submit did not complete")
            runtime.record_step(step=phase, status="ok", tool="browser", detail="submitted booking")

        result = existing_reservation_for_window(start, end, args.station_name, args.model_preference)
        if not result:
            raise BookingWindowError("failed: reservation completed page appeared, but reservation list verification failed")
        message = format_report(result)
        runtime.finish("ok", "done", final_message=message)
        print(message)
        return 0
    except Exception as exc:
        runtime.record_step(step=phase, status="failed", tool="browser", detail=str(exc))
        runtime.finish("failed", phase, final_message=str(exc))
        print(f"TimesCar 预订失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
