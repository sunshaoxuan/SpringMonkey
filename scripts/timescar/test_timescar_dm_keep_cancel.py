#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import timescar_handle_dm_adjust_request as mod


TZ = ZoneInfo("Asia/Tokyo")


def fake_reservation(start: datetime) -> dict:
    return {
        "bookingNumber": "B123456",
        "start": start.isoformat(timespec="minutes"),
        "return": (start + timedelta(hours=3)).isoformat(timespec="minutes"),
        "station": "测试站点",
        "vehicle": "测试车辆",
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="timescar_dm_keep_cancel_") as tmp:
        mod.WORKSPACE = Path(tmp)
        mod.LEDGER_PATH = Path(tmp) / "var" / "timescar_dm_completed_requests.json"
        mod.DECISIONS_PATH = Path(tmp) / ".secure" / "timescar_user_decisions.json"
        mod.CANCEL_LEDGER_PATH = Path(tmp) / "var" / "timescar_dm_cancelled_requests.json"
        message_time = datetime(2026, 5, 4, 18, 0, tzinfo=TZ)
        reservations = [fake_reservation(message_time + timedelta(hours=12))]
        original_fetch = mod.fetch_reservations
        original_run_canceller = mod.run_canceller
        original_run_booker = mod.run_booker
        try:
            mod.fetch_reservations = lambda: reservations
            mod.run_booker = lambda start, end, force: subprocess.CompletedProcess(
                args=["timescar_book_reservation_window.py"],
                returncode=0,
                stdout=(
                    "TimesCar 预订结果\n"
                    "状态：预约已提交并回查确认\n"
                    "预约编号：B654321\n"
                    f"预约开始：{start.strftime('%Y-%m-%dT%H:%M')}\n"
                    f"返却予定：{end.strftime('%Y-%m-%dT%H:%M')}"
                ),
                stderr="",
            )
            mod.run_canceller = lambda booking, current_start, force: subprocess.CompletedProcess(
                args=["timescar_cancel_reservation.py"],
                returncode=0,
                stdout=(
                    "TimesCar 取消预约结果\n"
                    "状态：预约取消已提交并回查确认\n"
                    f"预约编号：{booking}\n"
                    f"开始：{current_start.strftime('%Y-%m-%dT%H:%M')}"
                ),
                stderr="",
            )
            book = mod.format_book_result("请再预订一单明天早9点到21点的车辆，车型和我惯用的一致。", message_time, force=True)
            keep = mod.format_keep_result("请保留明天的订车", message_time)
            cancel = mod.format_cancel_result("请取消这单订车", message_time, force=True)
            reservations.clear()
            status = mod.format_cancel_status_result("这单取消了吗？", message_time)
        finally:
            mod.fetch_reservations = original_fetch
            mod.run_canceller = original_run_canceller
            mod.run_booker = original_run_booker
        assert "预约已提交并回查确认" in book
        assert "预约开始：2026-05-05T09:00" in book
        assert "已记录保留决定" in keep
        assert mod.DECISIONS_PATH.exists()
        data = json.loads(mod.DECISIONS_PATH.read_text(encoding="utf-8"))
        assert data["keepBookingNumbers"]["B123456"]["status"] == "keep"
        assert "预约取消已提交并回查确认" in cancel
        assert "预约编号：B123456" in cancel
        assert "已取消" in status
        assert "当前预约列表中已不存在该预约" in status
        assert mod.is_keep_request("请保留明天的订车")
        assert mod.is_book_request("请再预订一单明天早9点到21点的车辆，车型和我惯用的一致。")
        assert mod.is_cancel_request("请取消这单订车")
        assert mod.is_cancel_status_request("这单取消了吗？")
        assert not mod.is_cancel_request("请把明天开始的订车取消明天的时间，让开始时间从后天早上9点开始")
    print("timescar_dm_keep_cancel_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
