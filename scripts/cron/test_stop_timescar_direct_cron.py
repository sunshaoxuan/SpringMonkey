import os

import pytest

from stop_timescar_direct_cron import apply, remove_entries


TARGETS = (
    b'0 22 * * * root /usr/local/lib/openclaw/direct_cron_to_discord.py --name timescar-daily-report-2200\n'
    b'@daily openclaw python3 /var/lib/openclaw/repos/SpringMonkey/scripts/timescar/check.py\n'
)
OTHER = (
    b'# TimesCar history\r\n'
    b'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n'
    b'0 7 * * * root /usr/local/lib/openclaw/direct_cron_to_discord.py --name weather-report-jst-0700\n'
    b'0 17 * * * root /usr/local/lib/openclaw/direct_cron_to_discord.py --name news-digest-jst-1700\n'
    b'0 10 */3 * * root /usr/local/lib/openclaw/direct_cron_to_discord.py --name xhs-recommendation-every-3-days\n'
)


def test_only_timescar_cron_entries_removed():
    assert remove_entries(OTHER + TARGETS) == (OTHER, 2)
    assert remove_entries(OTHER) == (OTHER, 0)


def test_apply_backups_original_and_is_idempotent(tmp_path, monkeypatch):
    if os.name == 'nt':
        monkeypatch.setattr(os, 'fchown', lambda *_: None, raising=False)
        monkeypatch.setattr(os, 'fchmod', lambda *_: None, raising=False)
    cron_file = tmp_path / 'openclaw-direct-discord'
    backup_dir = tmp_path / 'backup'
    backup_dir.mkdir()
    cron_file.write_bytes(OTHER + TARGETS)

    count, backup_path = apply(cron_file, backup_dir)

    assert count == 2
    assert backup_path.parent == backup_dir
    assert backup_path.read_bytes() == OTHER + TARGETS
    assert cron_file.read_bytes() == OTHER
    assert apply(cron_file, backup_dir) == (0, None)
    assert list(backup_dir.iterdir()) == [backup_path]


def test_refuses_non_regular_cron_path(tmp_path):
    with pytest.raises(ValueError, match='regular cron file'):
        apply(tmp_path, tmp_path)
