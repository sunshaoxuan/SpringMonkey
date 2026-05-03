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

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from task_runtime import TimesCarTaskRuntime


WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")
SECRET_CMD = ["bash", str(WORKSPACE / "scripts" / "timescar_secret.sh")]
RESERVE_LIST_URL = "https://share.timescar.jp/view/reserve/list.jsp"
TZ = ZoneInfo("Asia/Tokyo")
JOB_NAME = "timescar-adjust-reservation-window"


class AdjustError(RuntimeError):
    pass


def run_json(cmd: list[str]) -> dict:
    raw = subprocess.check_output(cmd, text=True)
    return json.loads(raw)


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


def format_site_date(value: datetime) -> str:
    return value.strftime("%Y-%m-%d") + " 00:00:00.0"


def format_iso_minute(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M")


def select_first_available(page, selector: str, values: list[str]) -> None:
    last_error: Exception | None = None
    for value in values:
        for kwargs in ({"value": value}, {"label": value}):
            try:
                page.select_option(selector, **kwargs, timeout=5000)
                return
            except Exception as exc:
                last_error = exc
    options = page.locator(f"{selector} option").evaluate_all(
        "els => els.map(el => ({value: el.value, text: (el.textContent || '').trim()}))"
    )
    raise AdjustError(f"选项不可用：{selector} wanted={values} options={options}") from last_error


def select_datetime(page, prefix: str, value: datetime) -> None:
    page.select_option(f"#date{prefix}", format_site_date(value))
    page.wait_for_timeout(500)
    select_first_available(page, f"#hour{prefix}", [f"{value.hour:02d}", str(value.hour)])
    select_first_available(page, f"#minute{prefix}", [f"{value.minute:02d}", str(value.minute)])


def select_target_reservation(reservations: list[dict], booking_number: str | None, current_start: datetime) -> dict:
    matches = []
    for reservation in reservations:
        start_raw = str(reservation.get("start") or "")
        if booking_number and str(reservation.get("bookingNumber") or "") != booking_number:
            continue
        try:
            start = parse_iso_minute(start_raw)
        except Exception:
            continue
        if start != current_start:
            continue
        matches.append(reservation)
    if not matches:
        label = booking_number or format_iso_minute(current_start)
        raise AdjustError(f"未找到目标预约：{label}")
    matches.sort(key=lambda item: str(item.get("acceptedAt") or ""))
    return matches[-1]


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


def locate_change_rid(page, booking: str) -> str:
    booking_cell = page.locator(f"xpath=//span[@id='bookingId' and normalize-space(text())='{booking}']").first
    if booking_cell.count() == 0:
        raise AdjustError("目标预约在列表页未找到")
    booking_row = booking_cell.locator("xpath=ancestor::tr[1]")
    change_link = booking_row.locator("xpath=.//a[contains(@href, 'change.jsp?rid=')]").first
    if change_link.count() == 0:
        change_link = booking_row.locator(
            "xpath=following-sibling::tr[1]//a[contains(@href, 'change.jsp?rid=')]"
            " | following-sibling::tr[2]//a[contains(@href, 'change.jsp?rid=')]"
            " | following-sibling::tr[3]//a[contains(@href, 'change.jsp?rid=')]"
        ).first
    href = change_link.get_attribute("href") if change_link.count() else ""
    match = re.search(r"rid=(\d+)", href or "")
    if not match:
        raise AdjustError("未找到目标预约的变更入口")
    return match.group(1)


def assert_confirm_page(body: str, new_start: datetime, new_return: datetime) -> None:
    start_pattern = rf"利用開始日時\s*{new_start.year:04d}年{new_start.month:02d}月{new_start.day:02d}日（[^）]+）{new_start.hour:02d}:{new_start.minute:02d}"
    return_pattern = rf"返却予定日時\s*{new_return.year:04d}年{new_return.month:02d}月{new_return.day:02d}日（[^）]+）{new_return.hour:02d}:{new_return.minute:02d}"
    if "入力内容に誤りがあります" in body:
        raise AdjustError("变更表单校验失败")
    if not re.search(start_pattern, body):
        raise AdjustError("确认页开始时间不匹配")
    if not re.search(return_pattern, body):
        raise AdjustError("确认页结束时间不匹配")


def format_report(booking: str, old_start: datetime, old_return: datetime, new_start: datetime, new_return: datetime, dry_run: bool) -> str:
    status = "dry-run 校验成功，未提交" if dry_run else "预约变更已提交并回查确认"
    return "\n".join(
        [
            "TimesCar 预约变更结果",
            f"状态：{status}",
            f"预约编号：{booking}",
            f"原开始：{format_iso_minute(old_start)}",
            f"原结束：{format_iso_minute(old_return)}",
            f"新开始：{format_iso_minute(new_start)}",
            f"新结束：{format_iso_minute(new_return)}",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--booking-number")
    parser.add_argument("--current-start", required=True, help="YYYY-MM-DDTHH:MM in JST")
    parser.add_argument("--new-start", required=True, help="YYYY-MM-DDTHH:MM in JST")
    parser.add_argument("--new-return", help="YYYY-MM-DDTHH:MM in JST; defaults to current reservation return time")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.dry_run and args.force:
        raise SystemExit("--dry-run and --force are mutually exclusive")

    runtime = TimesCarTaskRuntime(JOB_NAME, "write", ttl_seconds=1800)
    phase = "init"
    try:
        runtime.start("fetch-reservations")
        reservations = fetch_reservations()
        current_start = parse_iso_minute(args.current_start)
        new_start = parse_iso_minute(args.new_start)
        target = select_target_reservation(reservations, args.booking_number, current_start)
        booking = str(target.get("bookingNumber") or "")
        old_return = parse_iso_minute(str(target.get("return") or ""))
        new_return = parse_iso_minute(args.new_return) if args.new_return else old_return
        runtime.record_step(step="select-target", status="ok", tool="timescar_fetch_reservations.py", detail=f"booking={booking}")

        if new_start >= new_return:
            raise AdjustError("新开始时间必须早于结束时间")

        p1, p2, password = load_credentials()
        runtime.record_step(step="load-credentials", status="ok", tool="timescar_secret.sh", detail="credentials loaded")

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

            rid = locate_change_rid(page, booking)
            runtime.record_step(step="locate-change-entry", status="ok", tool="browser", detail=f"rid={rid}")

            phase = "prepare-change"
            page.goto(f"https://share.timescar.jp/view/reserve/change.jsp?rid={rid}", wait_until="domcontentloaded", timeout=60000)
            select_datetime(page, "Start", new_start)
            select_datetime(page, "End", new_return)
            page.locator("#doCheck").click()
            page.wait_for_load_state("domcontentloaded")
            body = page.locator("body").inner_text()
            assert_confirm_page(body, new_start, new_return)
            runtime.record_step(step=phase, status="ok", tool="browser", detail="confirm page verified")

            if args.dry_run or not args.force:
                message = format_report(booking, current_start, old_return, new_start, new_return, dry_run=True)
                runtime.finish("ok", "dry-run", final_message=message)
                print(message)
                return 0

            phase = "submit-change"
            page.locator("#doOnceRegist").click(force=True)
            page.wait_for_load_state("domcontentloaded")
            body = page.locator("body").inner_text()
            if "ご注意ください！" in body and page.locator("text=了解").count():
                page.locator("text=了解").click(force=True)
                page.wait_for_load_state("domcontentloaded")
                body = page.locator("body").inner_text()
                if "予約変更を受付けました。" not in body and page.locator("#doOnceRegist").count():
                    page.locator("#doOnceRegist").click(force=True)
                    page.wait_for_load_state("domcontentloaded")
                    body = page.locator("body").inner_text()
            if "予約変更を受付けました。" not in body:
                raise AdjustError("提交后未看到预约变更完成提示")
            runtime.record_step(step=phase, status="ok", tool="browser", detail="submitted change")

        refreshed = [item for item in fetch_reservations() if str(item.get("bookingNumber") or "") == booking]
        if not refreshed:
            raise AdjustError("提交后回查未找到目标预约")
        result = refreshed[0]
        verified_start = parse_iso_minute(str(result.get("start") or ""))
        verified_return = parse_iso_minute(str(result.get("return") or ""))
        if verified_start != new_start or verified_return != new_return:
            raise AdjustError(
                "提交后回查时间不匹配："
                f"start={format_iso_minute(verified_start)} return={format_iso_minute(verified_return)}"
            )
        message = format_report(booking, current_start, old_return, new_start, new_return, dry_run=False)
        runtime.finish("ok", "done", final_message=message)
        print(message)
        return 0
    except Exception as exc:
        runtime.record_step(step=phase, status="failed", tool="browser", detail=str(exc))
        runtime.finish("failed", phase, final_message=str(exc))
        print(f"TimesCar 预约变更失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
