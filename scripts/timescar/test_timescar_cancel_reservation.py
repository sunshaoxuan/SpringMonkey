#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import timescar_cancel_reservation as mod


TZ = ZoneInfo("Asia/Tokyo")


def main() -> int:
    start = datetime(2026, 5, 5, 9, 0, tzinfo=TZ)
    return_at = start + timedelta(hours=36)
    body = "\n".join(
        [
            "予約取消（確認）",
            "取消はまだ完了していません。",
            "以下の予約を取消します。取消確定ボタンを押してください。",
            "予約番号\t213063887",
            "利用開始日時\t2026年05月05日（火）09:00",
            "返却予定日時\t2026年05月06日（水）21:00",
        ]
    )
    mod.assert_cancel_confirm_page(body, "213063887", start, return_at)
    report = mod.format_cancel_report("213063887", start, return_at, dry_run=True)
    assert "dry-run 校验成功，未提交取消" in report
    assert "预约编号：213063887" in report
    assert "2026-05-05T09:00" in report
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert 'record_step("select-target"' not in source
    assert "record_step(step=" in source

    bad_body = body.replace("213063887", "000000000")
    try:
        mod.assert_cancel_confirm_page(bad_body, "213063887", start, return_at)
    except mod.CancelError:
        pass
    else:
        raise AssertionError("expected booking mismatch to fail")

    print("timescar_cancel_reservation_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
