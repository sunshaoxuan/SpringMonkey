#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import timescar_next24h_notice as notice


def main() -> int:
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    reservation = {
        "start": (now + timedelta(hours=2)).isoformat(),
        "startText": "2026年04月24日（金）09:00",
        "returnText": "2026年04月24日（金）21:00",
        "station": "久我山４丁目２",
        "vehicle": "ヤリスクロス",
        "bookingNumber": "123456789",
    }
    raw = '{"reservations": [' + __import__("json").dumps(reservation, ensure_ascii=False) + "]}"
    data = notice.extract_json(raw)
    assert len(data["reservations"]) == 1
    print("timescar_next24h_notice_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
