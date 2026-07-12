from datetime import datetime
from zoneinfo import ZoneInfo

from timescar_book_sat_3weeks import parse_reference_date, target_window


TZ = ZoneInfo("Asia/Tokyo")


def test_reference_date_replays_missed_friday_booking() -> None:
    reference = parse_reference_date("2026-07-11")
    assert reference == datetime(2026, 7, 11, tzinfo=TZ)
    start, end = target_window(reference)
    assert start.isoformat() == "2026-08-01T09:00:00+09:00"
    assert end.isoformat() == "2026-08-01T21:00:00+09:00"


def test_reference_date_is_optional() -> None:
    assert parse_reference_date(None) is None
