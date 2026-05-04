#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

from task_runtime import TimesCarTaskRuntime
from timescar_adjust_reservation_window import (
    RESERVE_LIST_URL,
    AdjustError,
    fetch_reservations,
    format_iso_minute,
    load_credentials,
    login_if_needed,
    parse_iso_minute,
    select_target_reservation,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

JOB_NAME = "timescar-cancel-reservation"


class CancelError(RuntimeError):
    pass


def locate_cancel_rid(page, booking: str) -> str:
    booking_cell = page.locator(f"xpath=//span[@id='bookingId' and normalize-space(text())='{booking}']").first
    if booking_cell.count() == 0:
        raise CancelError("目标预约在列表页未找到")
    booking_row = booking_cell.locator("xpath=ancestor::tr[1]")
    cancel_link = booking_row.locator("xpath=.//a[contains(@href, 'cancel.jsp?rid=')]").first
    if cancel_link.count() == 0:
        cancel_link = booking_row.locator(
            "xpath=following-sibling::tr[1]//a[contains(@href, 'cancel.jsp?rid=')]"
            " | following-sibling::tr[2]//a[contains(@href, 'cancel.jsp?rid=')]"
            " | following-sibling::tr[3]//a[contains(@href, 'cancel.jsp?rid=')]"
        ).first
    href = cancel_link.get_attribute("href") if cancel_link.count() else ""
    match = re.search(r"rid=(\d+)", href or "")
    if not match:
        raise CancelError("未找到目标预约的取消入口")
    return match.group(1)


def site_datetime_pattern(label: str, value: datetime) -> str:
    return rf"{label}\s*{value.year:04d}年{value.month:02d}月{value.day:02d}日（[^）]+）{value.hour:02d}:{value.minute:02d}"


def assert_cancel_confirm_page(body: str, booking: str, start: datetime, return_at: datetime) -> None:
    if "取消はまだ完了していません" not in body:
        raise CancelError("取消确认页未显示未完成提示")
    if "取消確定" not in body and "取消します" not in body:
        raise CancelError("取消确认页未显示取消确认提示")
    if not re.search(rf"予約番号\s*{re.escape(booking)}", body):
        raise CancelError("取消确认页预约编号不匹配")
    if not re.search(site_datetime_pattern("利用開始日時", start), body):
        raise CancelError("取消确认页开始时间不匹配")
    if not re.search(site_datetime_pattern("返却予定日時", return_at), body):
        raise CancelError("取消确认页结束时间不匹配")


def format_cancel_report(booking: str, start: datetime, return_at: datetime, dry_run: bool) -> str:
    status = "dry-run 校验成功，未提交取消" if dry_run else "预约取消已提交并回查确认"
    return "\n".join(
        [
            "TimesCar 取消预约结果",
            f"状态：{status}",
            f"预约编号：{booking}",
            f"开始：{format_iso_minute(start)}",
            f"结束：{format_iso_minute(return_at)}",
        ]
    )


def format_already_cancelled_report(booking: str, start: datetime) -> str:
    return "\n".join(
        [
            "TimesCar 取消预约结果",
            "状态：目标预约已不在当前预约列表中，视为无需重复取消",
            f"预约编号：{booking}",
            f"原开始：{format_iso_minute(start)}",
        ]
    )


def ensure_target_absent(booking: str) -> None:
    refreshed = [item for item in fetch_reservations() if str(item.get("bookingNumber") or "") == booking]
    if refreshed:
        raise CancelError("提交后回查仍能找到目标预约，取消未确认")


def run_browser_cancel(booking: str, start: datetime, return_at: datetime, dry_run: bool, force: bool) -> str:
    p1, p2, password = load_credentials()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:18800")
        ctx = browser.contexts[0]
        page = ctx.new_page()
        page.set_default_timeout(45000)
        page.goto(RESERVE_LIST_URL, wait_until="domcontentloaded", timeout=60000)
        login_if_needed(page, p1, p2, password)
        if page.url != RESERVE_LIST_URL:
            page.goto(RESERVE_LIST_URL, wait_until="domcontentloaded", timeout=60000)

        rid = locate_cancel_rid(page, booking)
        page.goto(urljoin(page.url, f"cancel.jsp?rid={rid}"), wait_until="domcontentloaded", timeout=60000)
        body = page.locator("body").inner_text()
        assert_cancel_confirm_page(body, booking, start, return_at)
        able_to_cancel = page.locator("#ableToCancel").get_attribute("value") if page.locator("#ableToCancel").count() else ""
        if able_to_cancel != "true":
            raise CancelError("站点返回 ableToCancel!=true，禁止提交取消")

        if dry_run or not force:
            return format_cancel_report(booking, start, return_at, dry_run=True)

        page.locator("#doOnceCancelComplete").click(force=True)
        page.wait_for_load_state("domcontentloaded")
        body = page.locator("body").inner_text()
        if "予約取消を受付けました" not in body and "予約取消完了" not in body and "取消完了" not in body:
            raise CancelError("提交后未看到预约取消完成提示")
    ensure_target_absent(booking)
    return format_cancel_report(booking, start, return_at, dry_run=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--booking-number", required=True)
    parser.add_argument("--current-start", required=True, help="YYYY-MM-DDTHH:MM in JST")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--allow-already-cancelled", action="store_true")
    args = parser.parse_args()
    if args.dry_run and args.force:
        raise SystemExit("--dry-run and --force are mutually exclusive")

    runtime = TimesCarTaskRuntime(JOB_NAME, "write", ttl_seconds=1800)
    phase = "init"
    try:
        runtime.start("fetch-reservations")
        current_start = parse_iso_minute(args.current_start)
        reservations = fetch_reservations()
        try:
            target = select_target_reservation(reservations, args.booking_number, current_start)
        except AdjustError:
            if args.allow_already_cancelled:
                message = format_already_cancelled_report(args.booking_number, current_start)
                runtime.finish("ok", "already-cancelled", final_message=message)
                print(message)
                return 0
            raise
        booking = str(target.get("bookingNumber") or "")
        return_at = parse_iso_minute(str(target.get("return") or ""))
        runtime.record_step("select-target", "ok", "timescar_fetch_reservations.py", f"booking={booking}")

        phase = "browser-cancel"
        message = run_browser_cancel(booking, current_start, return_at, args.dry_run, args.force)
        runtime.record_step(phase, "ok", "browser", "cancel flow verified" if args.dry_run or not args.force else "cancel submitted")
        runtime.finish("ok", "dry-run" if args.dry_run or not args.force else "done", final_message=message)
        print(message)
        return 0
    except Exception as exc:
        runtime.record_step(phase, "failed", "browser", str(exc))
        runtime.finish("failed", phase, final_message=str(exc))
        print(f"TimesCar 取消预约失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
