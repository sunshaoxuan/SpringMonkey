#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import timescar_book_reservation_window as mod
import timescar_book_sat_3weeks as sat_mod


TZ = ZoneInfo("Asia/Tokyo")


class FakeLocator:
    def __init__(self, page, selector: str):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    def count(self) -> int:
        if self.selector != "#licenseCaution_box .s_agree":
            return 0
        return 1

    def is_visible(self) -> bool:
        return self.count() > 0

    def click(self, force: bool = False) -> None:
        self.page.clicks += 1
        self.page.body = "予約登録を受け付けました。"

    def inner_text(self) -> str:
        return self.page.body


class FakePage:
    def __init__(self):
        self.body = "ご注意ください！"
        self.clicks = 0
        self.waits = 0

    def locator(self, selector: str):
        return FakeLocator(self, selector)

    def wait_for_load_state(self, state: str) -> None:
        self.waits += 1

    def wait_for_timeout(self, timeout_ms: int) -> None:
        self.waits += 1


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
    assert mod.booking_submit_completed("予約登録を受付けました。")
    assert mod.booking_submit_completed("予約登録を 受け付けました。")
    assert mod.booking_submit_completed("予約完了")
    assert not mod.booking_submit_completed("予約登録（確認）")
    assert sat_mod.booking_submit_completed("予約登録を受付けました。")
    assert sat_mod.booking_submit_completed("予約登録を 受け付けました。")
    assert sat_mod.booking_submit_completed("予約完了")
    assert not sat_mod.booking_submit_completed("予約登録（確認）")
    fake_page = FakePage()
    assert mod.confirm_attention_if_present(fake_page, fake_page.body) == "予約登録を受け付けました。"
    assert fake_page.clicks == 1
    fake_page = FakePage()
    assert sat_mod.confirm_attention_if_present(fake_page, fake_page.body) == "予約登録を受け付けました。"
    assert fake_page.clicks == 1
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
