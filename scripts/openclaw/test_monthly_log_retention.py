import os
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

from monthly_log_retention import archive_source, month_key, prune_oldest_archives, source_slug


def test_month_key_and_source_slug() -> None:
    stamp = datetime(2026, 6, 15, 12, 0).timestamp()
    assert month_key(stamp) == "2026-06"
    assert source_slug(Path("/var/log/openclaw")) == "var__log__openclaw"


def test_archives_previous_month_and_keeps_current_month(tmp_path: Path) -> None:
    source = tmp_path / "logs"
    archive_root = tmp_path / "archives"
    source.mkdir()
    old = source / "old.log"
    current = source / "current.log"
    old.write_text("old", encoding="utf-8")
    current.write_text("current", encoding="utf-8")
    old_stamp = datetime(2026, 6, 15, 12, 0).timestamp()
    current_stamp = datetime(2026, 7, 12, 12, 0).timestamp()
    os.utime(old, (old_stamp, old_stamp))
    os.utime(current, (current_stamp, current_stamp))

    written = archive_source(source, archive_root, "2026-07")

    assert not old.exists()
    assert current.exists()
    assert len(written) == 1
    with ZipFile(written[0]) as archive:
        assert archive.read("old.log") == b"old"


def test_disk_guard_deletes_oldest_archive_first(tmp_path: Path, monkeypatch) -> None:
    archive_root = tmp_path / "archives"
    archive_root.mkdir()
    oldest = archive_root / "2026-04.zip"
    newer = archive_root / "2026-05.zip"
    oldest.write_bytes(b"oldest")
    newer.write_bytes(b"newer")
    os.utime(oldest, (1, 1))
    os.utime(newer, (2, 2))
    free_values = iter((5.0, 12.0))
    monkeypatch.setattr("monthly_log_retention.free_percent", lambda _path: next(free_values))

    deleted = prune_oldest_archives(archive_root, 10.0)

    assert deleted == [oldest]
    assert not oldest.exists()
    assert newer.exists()
