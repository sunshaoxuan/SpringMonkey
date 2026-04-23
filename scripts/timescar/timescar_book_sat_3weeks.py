#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from task_runtime import TimesCarTaskRuntime


WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")
SECRET_CMD = ["bash", str(WORKSPACE / "scripts" / "timescar_secret.sh")]
RESERVE_INPUT_URL = "https://share.timescar.jp/view/reserve/input.jsp?scd=JV56"
TZ = ZoneInfo("Asia/Tokyo")
TARGET_STATION = "久我山４丁目２"
TARGET_MODEL = "ヤリスクロス（ハイブリッド）"
TARGET_IDENT = "1286"
TARGET_COLOR = "グレイッシュブルー"
JOB_NAME = "timescar-book-sat-3weeks"


class BookingError(RuntimeError):
    pass


def run(cmd: list[str]) -> dict:
    out = subprocess.check_output(cmd, text=True)
    return json.loads(out)


def load_credentials() -> tuple[str, str, str]:
    data = run(SECRET_CMD)
    p1, p2 = data["member_number_parts"]
    return p1, p2, data["password"]


def target_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(TZ)
    start = (now + timedelta(days=21)).replace(hour=9, minute=0, second=0, microsecond=0)
    end = start.replace(hour=21)
    return start, end


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


def find_model_value(page) -> str:
    for item in option_texts(page, "#carId"):
        if TARGET_MODEL in item["text"]:
            return item["value"]
    raise BookingError(f"failed: station has no {TARGET_MODEL}")


def existing_reservation_for_target() -> dict | None:
    data = json.loads(subprocess.check_output(["python3", str(WORKSPACE / "scripts" / "timescar_fetch_reservations.py")], text=True))
    start, _ = target_window()
    target_prefix = start.strftime("%Y-%m-%dT09:00")
    matches = [
        reservation
        for reservation in data.get("reservations", [])
        if reservation.get("station") == TARGET_STATION
        and reservation.get("vehicle") == "ヤリスクロス"
        and reservation.get("start", "").startswith(target_prefix)
    ]
    if not matches:
        return None
    matches.sort(key=lambda reservation: reservation.get("acceptedAt", ""))
    return matches[-1]


def format_report(reservation: dict, keep_same_car: str) -> str:
    return "\n".join(
        [
            "预约 1",
            f'- 预约编号：{reservation.get("bookingNumber", "")}',
            f'- 预约开始：{reservation.get("startText", "")}',
            f'- 返却予定：{reservation.get("returnText", "")}',
            f'- ステーション：{reservation.get("station", "")}',
            f'- 车辆：{reservation.get("vehicle", "")}',
            f'- 车牌/识别：{reservation.get("carIdentifier", "")}',
            f'- 车身颜色：{reservation.get("carColor", "")}',
            f"- 是否保留同车：{keep_same_car}",
        ]
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    runtime = TimesCarTaskRuntime(JOB_NAME, "write", ttl_seconds=1800)
    phase = "init"
    try:
        runtime.start("load-credentials")
        p1, p2, password = load_credentials()
        runtime.record_step(step="load-credentials", status="ok", tool="secret.sh", detail="loaded TimesCar credentials")
        target_start, target_end = target_window()
        if target_start.weekday() != 5:
            raise BookingError(f"failed: computed target is not Saturday ({target_start.date()})")
        existing = existing_reservation_for_target()
        runtime.record_step(step="check-existing-reservation", status="ok", tool="timescar_fetch_reservations.py", detail="checked for existing target reservation")
        if existing:
            keep_same_car = "是" if TARGET_IDENT in (existing.get("carIdentifier") or "") and TARGET_COLOR == existing.get("carColor") else "否"
            message = "已存在目标日期预约，无需重复预定。\n\n" + format_report(existing, keep_same_car)
            runtime.finish("skipped", "already-booked", final_message=message)
            print(message)
            return 0

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:18800")
            ctx = browser.contexts[0]
            page = ctx.new_page()
            page.set_default_timeout(45000)
            phase = "open-booking-page"
            page.goto(RESERVE_INPUT_URL, wait_until="domcontentloaded", timeout=60000)
            login_if_needed(page, p1, p2, password)
            if page.url != RESERVE_INPUT_URL:
                page.goto(RESERVE_INPUT_URL, wait_until="domcontentloaded", timeout=60000)
            runtime.record_step(step=phase, status="ok", tool="browser", detail="opened reservation input page")

            model_value = find_model_value(page)
            page.select_option("#carId", model_value)
            page.select_option("#dateStart", target_start.strftime("%Y-%m-%d 00:00:00.0"))
            page.select_option("#hourStart", "9")
            page.select_option("#minuteStart", "00")
            page.select_option("#dateEnd", target_end.strftime("%Y-%m-%d 00:00:00.0"))
            page.select_option("#hourEnd", "21")
            page.select_option("#minuteEnd", "00")
            page.check("#exemptNocFlgYes")

            phase = "validate-booking-form"
            page.locator("#doCheck").click()
            page.wait_for_load_state("domcontentloaded")
            text = page.locator("body").inner_text()
            if "入力内容に誤りがあります" in text:
                raise BookingError("failed: booking form validation error")
            if "予約登録（確認）" not in text and "予約登録(確認)" not in text:
                raise BookingError("failed: did not reach booking confirm page")
            runtime.record_step(step=phase, status="ok", tool="browser", detail="reached booking confirm page")

            confirm_match = re.search(r"利用開始日時\s*(\d{4})年(\d{2})月(\d{2})日（[^）]+）(\d{2}):(\d{2})", text)
            if not confirm_match:
                raise BookingError("failed: could not verify target reservation date on confirm page")
            confirm_date = f"{confirm_match.group(1)}-{confirm_match.group(2)}-{confirm_match.group(3)}"
            if confirm_date != target_start.strftime("%Y-%m-%d"):
                raise BookingError(f'failed: target date mismatch, expected {target_start.strftime("%Y-%m-%d")}, got {confirm_date}')

            if args.dry_run:
                runtime.finish("ok", "dry-run", final_message="dry-run ok")
                print("dry-run ok")
                return 0

            phase = "submit-booking"
            page.locator("#doOnceRegist").click()
            page.wait_for_load_state("domcontentloaded")
            done_text = page.locator("body").inner_text()
            if "予約登録を受付けました。" not in done_text:
                raise BookingError("failed: reservation submit did not complete")
            runtime.record_step(step=phase, status="ok", tool="browser", detail="submitted booking")

        result = existing_reservation_for_target()
        if not result:
            raise BookingError("failed: reservation completed page appeared, but reservation list verification failed")
        keep_same_car = "是" if TARGET_IDENT in (result.get("carIdentifier") or "") and TARGET_COLOR == result.get("carColor") else "否"
        message = format_report(result, keep_same_car)
        runtime.finish("ok", "done", final_message=message)
        print(message)
        return 0
    except BookingError as exc:
        runtime.record_step(step=phase, status="failed", tool="browser", detail=str(exc))
        runtime.finish("failed", phase, final_message=str(exc))
        print(str(exc))
        return 1
    except Exception as exc:
        runtime.record_step(step=phase, status="failed", tool="browser", detail=str(exc))
        runtime.finish("failed", phase, final_message=f"failed: {exc}")
        print(f"failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
