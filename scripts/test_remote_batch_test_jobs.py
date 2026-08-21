import importlib.util
import json
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("remote_batch_test_jobs.py")
SPEC = importlib.util.spec_from_file_location("remote_batch_test_jobs", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def test_policy_rejects_public_owner_overlap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "policy.json"
        path.write_text(
            json.dumps(
                {
                    "test_delivery_policy": "owner_dm_only",
                    "public_test_delivery_forbidden": True,
                    "owner_discord_dm_channel_ids": [mod.OWNER_DM],
                    "public_discord_channel_ids": [mod.OWNER_DM],
                }
            ),
            encoding="utf-8",
        )
        try:
            mod.load_policy(path)
        except RuntimeError as exc:
            assert "invalid" in str(exc)
        else:
            raise AssertionError("overlapping public and private channels must fail")


def test_direct_cron_plan_forces_write_jobs_to_dry_run() -> None:
    command, detail = mod.isolated_command(
        "timescar-book-sat-3weeks",
        ["python3", "/repo/scripts/timescar/timescar_book_sat_3weeks.py"],
    )
    assert command and command[-1] == "--dry-run"
    assert "submit disabled" in detail


def test_news_plan_uses_test_mode_without_published_state() -> None:
    command, detail = mod.isolated_command("news-digest-jst-0900", ["unsafe-wrapper"])
    assert command
    assert command[-3:] == ["--broadcast-mode", "test", "--no-record-recent"]
    assert "no published-state update" in detail


def test_public_direct_target_is_planned_without_public_delivery() -> None:
    entry = {
        "name": "weather-report-jst-0700",
        "channel_id": "1483636573235843072",
        "command": ["python3", "weather.py"],
    }
    result = mod.test_direct_entry(entry, {"1483636573235843072"}, execute=False, timeout=1)
    assert result.status == "pass"
    assert result.mode == "plan"


def test_unknown_job_is_blocked_from_execution() -> None:
    entry = {"name": "unknown-write-job", "channel_id": mod.OWNER_DM, "command": ["dangerous"]}
    result = mod.test_direct_entry(entry, {"1483636573235843072"}, execute=True, timeout=1)
    assert result.status == "blocked"
    assert result.mode == "contract_only"


def test_direct_cron_parser_preserves_run_user_boundary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cron"
        path.write_text(
            "0 7 * * * root helper --name weather-report-jst-0700 --channel-id 1483636573235843072 --run-as-openclaw --command python3 weather.py\n",
            encoding="utf-8",
        )
        entries = mod.direct_cron_entries(path)
        assert entries[0]["run_as_openclaw"] is True


if __name__ == "__main__":
    test_policy_rejects_public_owner_overlap()
    test_direct_cron_plan_forces_write_jobs_to_dry_run()
    test_news_plan_uses_test_mode_without_published_state()
    test_public_direct_target_is_planned_without_public_delivery()
    test_unknown_job_is_blocked_from_execution()
    test_direct_cron_parser_preserves_run_user_boundary()
    print("remote_batch_test_jobs_ok")
