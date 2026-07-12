from __future__ import annotations

import argparse
import gzip
import os
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

from scheduled_log_retention import run_retention


def test_runs_once_daily_archives_old_files_and_journal(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    source = tmp_path / "logs"
    source.mkdir()
    old = source / "old.log"
    current = source / "current.log"
    old.write_text("old", encoding="utf-8")
    current.write_text("current", encoding="utf-8")
    os.utime(old, (datetime(2026, 6, 15).timestamp(),) * 2)
    os.utime(current, (datetime(2026, 7, 12).timestamp(),) * 2)
    journal = tmp_path / "journal.txt"
    journal.write_text("previous month journal\n", encoding="utf-8")
    args = argparse.Namespace(
        repo_root=repo_root,
        state_file=tmp_path / "state.json",
        archive_root=tmp_path / "archives",
        source=[source],
        journal_file=journal,
        journal_unit="openclaw.service",
        journal_online_days=35,
        min_free_percent=0.0,
        timeout=60,
        force=False,
    )

    first = run_retention(args, datetime(2026, 7, 12, 12, 0).astimezone())
    second = run_retention(args, datetime(2026, 7, 12, 13, 0).astimezone())

    assert first["status"] == "completed"
    assert second["status"] == "already_completed"
    assert not old.exists()
    assert current.exists()
    archives = list((tmp_path / "archives").rglob("2026-06.zip"))
    assert len(archives) == 1
    with ZipFile(archives[0]) as bundle:
        assert bundle.read("old.log") == b"old"
    journal_archives = list((tmp_path / "archives" / "journal").glob("*.journal.gz"))
    assert len(journal_archives) == 1
    with gzip.open(journal_archives[0], "rt", encoding="utf-8") as archived_journal:
        assert archived_journal.read() == "previous month journal\n"
