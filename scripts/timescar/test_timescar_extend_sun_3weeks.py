#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

import timescar_extend_sun_3weeks as mod


TZ = ZoneInfo("Asia/Tokyo")


def test_fetch_reservations_retries_and_uses_sibling_script() -> None:
    calls: list[list[str]] = []
    original = mod.subprocess.check_output
    original_sleep = mod.time.sleep
    try:
        def fake_check_output(cmd, **kwargs):
            calls.append(list(cmd))
            if len(calls) == 1:
                raise subprocess.CalledProcessError(1, cmd, output="temporary entry failure")
            return json.dumps({"reservations": [{"bookingNumber": "B1"}]}, ensure_ascii=False)

        mod.subprocess.check_output = fake_check_output
        mod.time.sleep = lambda _seconds: None
        reservations = mod.fetch_reservations(attempts=2, delay_seconds=0)
    finally:
        mod.subprocess.check_output = original
        mod.time.sleep = original_sleep

    assert reservations == [{"bookingNumber": "B1"}]
    assert len(calls) == 2
    assert calls[0][1].endswith("timescar_fetch_reservations.py")
    assert "/workspace/scripts/" not in calls[0][1].replace("\\", "/")


def test_select_target_reservation_uses_expected_sat_only_before_extension() -> None:
    reference = datetime(2026, 5, 10, tzinfo=TZ)
    target_start, target_sat_end, target_sun_end = mod.target_window(reference)
    reservations = [
        {
            "bookingNumber": "already-extended",
            "station": mod.TARGET_STATION,
            "vehicle": mod.TARGET_MODEL,
            "start": target_start,
            "return": target_sun_end,
            "acceptedAt": "2026-05-01T00:00",
        },
        {
            "bookingNumber": "target",
            "station": mod.TARGET_STATION,
            "vehicle": mod.TARGET_MODEL,
            "start": target_start,
            "return": target_sat_end,
            "acceptedAt": "2026-05-02T00:00",
        },
    ]
    original = mod.fetch_reservations
    try:
        mod.fetch_reservations = lambda: reservations
        selected = mod._select_target_reservation_with_reference(reference)
    finally:
        mod.fetch_reservations = original

    assert selected and selected["bookingNumber"] == "target"


def test_change_submit_completion_markers_are_tolerant() -> None:
    assert mod.change_submit_completed("予約変更を受付けました。")
    assert mod.change_submit_completed("予約変更を 受け付けました。")
    assert mod.change_submit_completed("変更完了")
    assert not mod.change_submit_completed("予約変更（確認）")


def test_extract_validation_blocker_reports_no_availability() -> None:
    body = "入力内容に誤りがあります\n予約できない期間が含まれていますので、空き状況をご確認ください。"
    assert mod.extract_validation_blocker(body) == "目标延长时段包含不可预约区间，TimesCar 页面拒绝延长。"
    assert mod.extract_validation_blocker("入力内容に誤りがあります") == "TimesCar 修改页返回输入校验错误。"


if __name__ == "__main__":
    test_fetch_reservations_retries_and_uses_sibling_script()
    test_select_target_reservation_uses_expected_sat_only_before_extension()
    test_change_submit_completion_markers_are_tolerant()
    test_extract_validation_blocker_reports_no_availability()
    print("timescar_extend_sun_3weeks_ok")
