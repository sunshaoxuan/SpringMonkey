#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

def extract_json(raw: str) -> dict:
    raw = raw.strip()
    if not raw:
        raise ValueError("empty output")
    try:
        import json
        return json.loads(raw)
    except Exception:
        pass
    import re
    m = re.search(r"(\{[\s\S]*\})\s*$", raw)
    if not m:
        raise ValueError(f"no trailing json object found in: {raw[:200]}...")
    import json
    return json.loads(m.group(1))

from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from task_runtime import TimesCarTaskRuntime


WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")
SECRET_CMD = ["bash", str(WORKSPACE / "scripts" / "timescar_secret.sh")]
RESERVE_LIST_URL = "https://share.timescar.jp/view/reserve/list.jsp"
TZ = ZoneInfo("Asia/Tokyo")
TARGET_STATION = "久我山４丁目２"
TARGET_MODEL = "ヤリスクロス"
TARGET_IDENT = "1286"
TARGET_COLOR = "グレイッシュブルー"
JOB_NAME = "timescar-extend-sun-3weeks"


class ExtendError(RuntimeError):
    pass


def run_json(cmd: list[str]) -> dict:
    return extract_json(subprocess.check_output(cmd, text=True))


def load_credentials() -> tuple[str, str, str]:
    data = run_json(SECRET_CMD)
    p1, p2 = data["member_number_parts"]
    return p1, p2, data["password"]


def target_window(now: datetime | None = None) -> tuple[str, str, str]:
    now = now or datetime.now(TZ)
    start = (now + timedelta(days=20)).replace(hour=9, minute=0, second=0, microsecond=0)
    sat_end = start.replace(hour=21)
    sun_end = sat_end + timedelta(days=1)
    return start.strftime("%Y-%m-%dT09:00"), sat_end.strftime("%Y-%m-%dT21:00"), sun_end.strftime("%Y-%m-%dT21:00")


def parse_reference_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=TZ)


def fetch_reservations() -> list[dict]:
    data = json.loads(subprocess.check_output(["python3", str(WORKSPACE / "scripts" / "timescar_fetch_reservations.py")], text=True))
    return data.get("reservations", [])


def _select_target_reservation_with_reference(reference_now: datetime) -> dict | None:
    target_start, target_sat_end, _ = target_window(reference_now)
    matches = [
        reservation
        for reservation in fetch_reservations()
        if reservation.get("station") == TARGET_STATION
        and reservation.get("vehicle") == TARGET_MODEL
        and reservation.get("start", "").startswith(target_start)
        and reservation.get("return", "").startswith(target_sat_end)
    ]
    if not matches:
        return None
    matches.sort(key=lambda reservation: reservation.get("acceptedAt", ""))
    return matches[-1]


def select_target_reservation() -> dict | None:
    return _select_target_reservation_with_reference(datetime.now(TZ))


def format_report(reservation: dict) -> str:
    keep_same_car = "是" if TARGET_IDENT in (reservation.get("carIdentifier") or "") and reservation.get("carColor") == TARGET_COLOR else "否"
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reference-date", help="Anchor date in JST, format YYYY-MM-DD")
    args = ap.parse_args()

    runtime = TimesCarTaskRuntime(JOB_NAME, "write", ttl_seconds=1800)
    reference_now = parse_reference_date(args.reference_date)
    phase = "init"
    try:
        runtime.start("load-credentials")
        p1, p2, password = load_credentials()
        runtime.record_step(step="load-credentials", status="ok", tool="secret.sh", detail="loaded TimesCar credentials")
        target = select_target_reservation() if reference_now is None else _select_target_reservation_with_reference(reference_now)
        runtime.record_step(step="select-target-reservation", status="ok", tool="timescar_fetch_reservations.py", detail="selected Saturday reservation for extension")
        if not target:
            message = "未找到目标日期的周六 09:00-21:00 预约，无需延长。"
            runtime.finish("skipped", "no-match", final_message=message)
            print(message)
            return 0

        _, _, target_sun_end = target_window(reference_now)
        rid = None
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:18800")
            ctx = browser.contexts[0]
            page = ctx.new_page()
            page.set_default_timeout(45000)
            phase = "open-reservation-list"
            page.goto(RESERVE_LIST_URL, wait_until="domcontentloaded", timeout=60000)
            login_if_needed(page, p1, p2, password)
            if page.url != RESERVE_LIST_URL:
                page.goto(RESERVE_LIST_URL, wait_until="domcontentloaded", timeout=60000)
            runtime.record_step(step=phase, status="ok", tool="browser", detail="opened reservation list")

            booking = target["bookingNumber"]
            booking_cell = page.locator(f"xpath=//span[@id='bookingId' and normalize-space(text())='{booking}']").first
            if booking_cell.count() == 0:
                raise ExtendError("failed: target reservation row not found on reservation list")
            booking_row = booking_cell.locator("xpath=ancestor::tr[1]")
            change_link = booking_row.locator("xpath=.//a[contains(@href, 'change.jsp?rid=')]").first
            if change_link.count() == 0:
                change_link = booking_row.locator("xpath=following-sibling::tr[1]//a[contains(@href, 'change.jsp?rid=')] | following-sibling::tr[2]//a[contains(@href, 'change.jsp?rid=')] | following-sibling::tr[3]//a[contains(@href, 'change.jsp?rid=')]").first
            href = change_link.get_attribute("href") if change_link.count() else None
            if href:
                m = re.search(r"rid=(\d+)", href)
                if m:
                    rid = m.group(1)
            if not rid:
                raise ExtendError("failed: could not locate change entry for target reservation")
            runtime.record_step(step="locate-change-entry", status="ok", tool="browser", detail=f"rid={rid}")

            phase = "prepare-extension"
            page.goto(f"https://share.timescar.jp/view/reserve/change.jsp?rid={rid}", wait_until="domcontentloaded", timeout=60000)
            page.select_option("#dateEnd", target_sun_end[:10] + " 00:00:00.0")
            page.select_option("#hourEnd", "21")
            page.select_option("#minuteEnd", "00")
            page.locator("#doCheck").click()
            page.wait_for_load_state("domcontentloaded")
            txt = page.locator("body").inner_text()
            if "入力内容に誤りがあります" in txt:
                raise ExtendError("failed: extension form validation error")
            confirm_end = re.search(r"返却予定日時\s*(\d{4})年(\d{2})月(\d{2})日（[^）]+）(\d{2}):(\d{2})", txt)
            if not confirm_end:
                raise ExtendError("failed: could not verify extension confirm page")
            confirm_date = f"{confirm_end.group(1)}-{confirm_end.group(2)}-{confirm_end.group(3)}T{confirm_end.group(4)}:{confirm_end.group(5)}"
            if not confirm_date.startswith(target_sun_end[:16]):
                raise ExtendError("failed: extension target end time mismatch")
            runtime.record_step(step=phase, status="ok", tool="browser", detail="verified extension confirm page")

            if args.dry_run:
                runtime.finish("ok", "dry-run", final_message="dry-run ok")
                print("dry-run ok")
                return 0

            phase = "submit-extension"
            page.locator("#doOnceRegist").click(force=True)
            page.wait_for_load_state("domcontentloaded")
            done = page.locator("body").inner_text()
            if "ご注意ください！" in done and page.locator("text=了解").count():
                page.locator("text=了解").click(force=True)
                page.locator("#doOnceRegist").click(force=True)
                page.wait_for_load_state("domcontentloaded")
                done = page.locator("body").inner_text()
            if "予約変更を受付けました。" not in done:
                raise ExtendError("failed: extension submit did not complete")
            runtime.record_step(step=phase, status="ok", tool="browser", detail="submitted extension")

        refreshed = [reservation for reservation in fetch_reservations() if reservation.get("bookingNumber") == target["bookingNumber"]]
        if not refreshed:
            raise ExtendError("failed: extension completed but reservation list verification failed")
        result = refreshed[0]
        message = format_report(result)
        runtime.finish("ok", "done", final_message=message)
        print(message)
        return 0
    except ExtendError as exc:
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
