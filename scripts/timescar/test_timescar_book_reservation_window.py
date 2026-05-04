#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import timescar_book_reservation_window as mod


TZ = ZoneInfo("Asia/Tokyo")


def main() -> int:
    start = datetime(2026, 5, 6, 9, 0, tzinfo=TZ)
    end = datetime(2026, 5, 6, 21, 0, tzinfo=TZ)
    body = "\n".join(
        [
            "予約登録（確認）",
            "利用開始日時\t2026年05月06日（水）09:00",
            "返却予定日時\t2026年05月06日（水）21:00",
            "久我山４丁目２",
            "ヤリスクロス（ハイブリッド）",
        ]
    )
    mod.assert_confirm_page(body, start, end, "久我山４丁目２", "ヤリスクロス（ハイブリッド）")
    mod.assert_confirm_page(body, start, end, "久我山４丁目２", "ベーシック／ヤリスクロス（ハイブリッド）")
    mod.assert_confirm_page(body, start, end, "久我山４丁目２", "ベーシック／ヤリスクロス（ハイブリッド）（1）")
    reservation = {
        "bookingNumber": "B999",
        "start": "2026-05-06T09:00",
        "return": "2026-05-06T21:00",
        "station": "久我山４丁目２",
        "vehicle": "ヤリスクロス",
        "carIdentifier": "杉並 300 ワ 1286",
        "carColor": "グレイッシュブルー",
    }
    assert mod.same_window(reservation, start, end, "久我山４丁目２", "ヤリスクロス（ハイブリッド）")
    assert mod.same_window(reservation, start, end, "久我山４丁目２", "any")
    report = mod.format_report(reservation)
    assert "预约已提交并回查确认" in report
    assert "是否保留同车：是" in report
    unavailable = mod.format_unavailable_report(start, end, "久我山４丁目２", "ヤリスクロス（ハイブリッド）", "not available")
    assert "未执行预订，目标窗口不可预订" in unavailable
    assert "not available" in unavailable

    try:
        mod.assert_confirm_page(body.replace("21:00", "20:00"), start, end, "久我山４丁目２", "ヤリスクロス（ハイブリッド）")
    except mod.BookingWindowError:
        pass
    else:
        raise AssertionError("expected return time mismatch to fail")

    print("timescar_book_reservation_window_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
