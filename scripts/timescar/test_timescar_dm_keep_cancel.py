#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
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
        message_time = datetime(2026, 5, 4, 18, 0, tzinfo=TZ)
        reservations = [fake_reservation(message_time + timedelta(hours=12))]
        original_fetch = mod.fetch_reservations
        try:
            mod.fetch_reservations = lambda: reservations
            keep = mod.format_keep_result("请保留明天的订车", message_time)
            cancel = mod.format_cancel_result("请取消这单订车", message_time)
        finally:
            mod.fetch_reservations = original_fetch
        assert "已记录保留决定" in keep
        assert mod.DECISIONS_PATH.exists()
        data = json.loads(mod.DECISIONS_PATH.read_text(encoding="utf-8"))
        assert data["keepBookingNumbers"]["B123456"]["status"] == "keep"
        assert "未执行取消" in cancel
        assert "没有已验证的 TimesCar 取消提交执行器" in cancel
        assert mod.is_keep_request("请保留明天的订车")
        assert mod.is_cancel_request("请取消这单订车")
        assert not mod.is_cancel_request("请把明天开始的订车取消明天的时间，让开始时间从后天早上9点开始")
    print("timescar_dm_keep_cancel_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
