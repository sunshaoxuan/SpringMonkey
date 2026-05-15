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
        reservations = [fake_reservation(datetime(2026, 5, 5, 9, 0, tzinfo=TZ))]
        original_fetch = mod.fetch_reservations
        original_run_canceller = mod.run_canceller
        original_run_booker = mod.run_booker
        original_run_adjuster = mod.run_adjuster
        original_classify_adjust_contract = mod.classify_adjust_contract
        adjust_calls = []
        try:
            mod.fetch_reservations = lambda: reservations
            mod.run_booker = lambda start, end, force, model_preference: subprocess.CompletedProcess(
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
            def fake_adjuster(booking, current_start, new_start, force, new_return=None):
                adjust_calls.append((booking, current_start, new_start, force, new_return))
                return subprocess.CompletedProcess(
                    args=["timescar_adjust_reservation_window.py"],
                    returncode=0,
                    stdout=(
                        "TimesCar 预约变更结果\n"
                        "状态：预约变更已提交并回查确认\n"
                        f"预约编号：{booking}\n"
                        f"原开始：{current_start.strftime('%Y-%m-%dT%H:%M')}\n"
                        f"新开始：{new_start.strftime('%Y-%m-%dT%H:%M')}"
                    ),
                    stderr="",
                )

            mod.run_adjuster = fake_adjuster
            def fake_adjust_contract(text, message_time, reservations, *, model_caller=None):
                if "整体" in text:
                    return {
                        "supported": True,
                        "operation": "shift_window",
                        "target": {"selector": "next_within_hours", "booking_number": None, "relative_days": None, "within_hours": 48},
                        "start_shift_minutes": 15,
                        "new_start_local": None,
                        "preserve_return_time": False,
                        "shift_return_time": True,
                        "confidence": 0.95,
                        "reason": "test semantic contract",
                    }
                return {
                    "supported": True,
                    "operation": "adjust_start",
                    "target": {"selector": "relative_day_unique_reservation", "booking_number": None, "relative_days": 1, "within_hours": None},
                    "start_shift_minutes": 24 * 60,
                    "new_start_local": None,
                    "preserve_return_time": True,
                    "shift_return_time": False,
                    "confidence": 0.95,
                    "reason": "test semantic contract",
                }

            mod.classify_adjust_contract = fake_adjust_contract
            book = mod.format_book_result("请再预订一单明天早9点到21点的车辆，车型和我惯用的一致。", message_time, force=True)
            book_any = mod.format_book_result("那就把车换成可以预订的车", message_time, force=True)
            keep = mod.format_keep_result("请保留明天的订车", message_time)
            relative_adjust = mod.format_adjust_result("把这单的开始时间往后推24小时，结束时间不变。", message_time, force=True)
            tomorrow_relative_adjust = mod.format_adjust_result(
                "请把明天开始的 TimesCar 订车预约的开始时间往后延 24 小时，结束时间保持不变。",
                message_time,
                force=True,
            )
            shift_window = mod.format_shift_window_result("请把马上开始的那单预订帮我往后整体延15分钟。", message_time, force=True)
            cancel = mod.format_cancel_result("请取消这单订车", message_time, force=True)
            cancel_followup = mod.format_cancel_result("好的，把刚刚这单取消掉吧", message_time, force=True)
            reservations.clear()
            status = mod.format_cancel_status_result("这单取消了吗？", message_time)
        finally:
            mod.fetch_reservations = original_fetch
            mod.run_canceller = original_run_canceller
            mod.run_booker = original_run_booker
            mod.run_adjuster = original_run_adjuster
            mod.classify_adjust_contract = original_classify_adjust_contract
        assert "预约已提交并回查确认" in book
        assert "预约开始：2026-05-05T09:00" in book
        assert "预约已提交并回查确认" in book_any
        assert "已记录保留决定" in keep
        assert mod.DECISIONS_PATH.exists()
        data = json.loads(mod.DECISIONS_PATH.read_text(encoding="utf-8"))
        assert data["keepBookingNumbers"]["B123456"]["status"] == "keep"
        assert "预约变更已提交并回查确认" in relative_adjust
        assert adjust_calls == [
            (
                "B123456",
                datetime(2026, 5, 5, 9, 0, tzinfo=TZ),
                datetime(2026, 5, 6, 9, 0, tzinfo=TZ),
                True,
                None,
            ),
            (
                "B123456",
                datetime(2026, 5, 5, 9, 0, tzinfo=TZ),
                datetime(2026, 5, 6, 9, 0, tzinfo=TZ),
                True,
                None,
            ),
            (
                "B123456",
                datetime(2026, 5, 5, 9, 0, tzinfo=TZ),
                datetime(2026, 5, 5, 9, 15, tzinfo=TZ),
                True,
                datetime(2026, 5, 5, 12, 15, tzinfo=TZ),
            )
        ]
        assert "预约变更已提交并回查确认" in tomorrow_relative_adjust
        assert "预约变更已提交并回查确认" in shift_window
        assert "预约取消已提交并回查确认" in cancel
        assert "预约编号：B123456" in cancel
        assert "预约取消已提交并回查确认" in cancel_followup
        assert "已取消" in status
        assert "当前预约列表中已不存在该预约" in status
        assert mod.is_keep_request("请保留明天的订车")
        assert mod.is_book_request("请再预订一单明天早9点到21点的车辆，车型和我惯用的一致。")
        assert mod.is_book_request("那就把车换成可以预订的车")
        assert mod.book_model_preference("那就把车换成可以预订的车") == "any"
        assert mod.is_cancel_request("请取消这单订车")
        assert mod.is_cancel_request("好的，把刚刚这单取消掉吧")
        assert mod.is_cancel_request("把这单取消掉")
        assert mod.is_cancel_status_request("这单取消了吗？")
        assert mod.is_adjust_request("请把明天开始的订车改到后天早9点")
        assert mod.is_adjust_request("请把明天开始的订车取消明天的时间，让开始时间从后天早上9点开始")
        assert mod.is_adjust_request("把这单的开始时间往后推24小时，结束时间不变。")
        assert mod.is_adjust_request("请把明天开始的 TimesCar 订车预约的开始时间往后延 24 小时，结束时间保持不变。")
        assert mod.is_whole_window_shift_request("请把马上开始的那单预订帮我往后整体延15分钟。")
        assert mod.is_adjust_request("请把马上开始的那单预订帮我往后整体延15分钟。")
        assert not mod.is_cancel_request("请把明天开始的订车取消明天的时间，让开始时间从后天早上9点开始")
        assert not mod.is_adjust_request("好的，把刚刚这单取消掉吧")
        assert mod.parse_query_hours("查一下未来一周的订车记录") == 24 * 7
        assert mod.parse_query_hours("未来一週間のTimesCar予約を確認して") == 24 * 7
        assert mod.parse_query_hours("查一下未来2周的订车记录") == 24 * 14
        assert mod.parse_query_hours("查一下未来两周的订车记录") == 24 * 14
        assert mod.parse_query_hours("未来三週間のTimesCar予約を確認して") == 24 * 21
        assert mod.parse_query_hours("查一下未来十天的订车记录") == 24 * 10
        assert mod.parse_query_hours("查询 TimesCar 预约 一个月的") == 24 * 30
        assert mod.parse_query_hours("未来1ヶ月のTimesCar予約を確認して") == 24 * 30
        assert mod.parse_query_window("未来一个月以后的订车记录") == (24 * 30, 24 * 30)
        contract = mod.classify_adjust_contract(
            "请把明天开始的 TimesCar 订车预约的开始时间往后延 24 小时，结束时间保持不变。",
            message_time,
            reservations,
            model_caller=lambda _messages: json.dumps(
                {
                    "supported": True,
                    "operation": "adjust_start",
                    "target": {"selector": "relative_day_unique_reservation", "booking_number": None, "relative_days": 1, "within_hours": None},
                    "start_shift_minutes": 1440,
                    "new_start_local": None,
                    "preserve_return_time": True,
                    "shift_return_time": False,
                    "confidence": 0.96,
                    "reason": "semantic parser test",
                },
                ensure_ascii=False,
            ),
        )
        assert contract["operation"] == "adjust_start"
        assert contract["target"]["selector"] == "relative_day_unique_reservation"
        try:
            mod.classify_adjust_contract(
                "随便处理一下这单",
                message_time,
                reservations,
                model_caller=lambda _messages: json.dumps(
                    {
                        "supported": False,
                        "operation": "unsupported",
                        "target": {"selector": "next_within_hours", "booking_number": None, "relative_days": None, "within_hours": 48},
                        "start_shift_minutes": None,
                        "new_start_local": None,
                        "preserve_return_time": None,
                        "shift_return_time": None,
                        "confidence": 0.4,
                        "reason": "ambiguous request",
                    },
                    ensure_ascii=False,
                ),
            )
            raise AssertionError("unsupported TimesCar text must not be accepted")
        except mod.IntentError:
            pass
    print("timescar_dm_keep_cancel_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
