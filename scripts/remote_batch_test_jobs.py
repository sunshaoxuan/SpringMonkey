#!/usr/bin/env python3
"""Safely test OpenClaw scheduled jobs without touching public delivery.

The runner discovers the current OpenClaw cron catalog and direct cron file at
runtime.  It never edits a formal cron job and never calls ``openclaw cron
run``.  Known business commands are executed directly in an isolated test
mode.  Write-capable TimesCar jobs are forced to ``--dry-run``.  Unknown jobs
receive contract validation and are reported as blocked instead of being run.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OWNER_DM = "1497009159940608020"
PUBLIC_CHANNELS = {"1483636573235843072"}
DEFAULT_OUTPUT = Path("/var/lib/openclaw/.openclaw/logs/private_cron_tests/latest.json")
DEFAULT_DIRECT_CRON = Path("/etc/cron.d/openclaw-direct-discord")
DEFAULT_ENV_FILE = Path("/etc/openclaw/openclaw.env")
DEFAULT_MIGRATION_CONFIG = Path(__file__).resolve().parents[1] / "config" / "openclaw" / "official_runtime_migration.json"

READ_ONLY_JOBS = {
    "weather-report-jst-0700",
    "news-digest-jst-0900",
    "news-digest-jst-1700",
    "timescar-daily-report-2200",
    "timescar-ask-cancel-next24h-2300",
    "timescar-ask-cancel-next24h-0000",
    "timescar-ask-cancel-next24h-0100",
    "timescar-ask-cancel-next24h-0700",
    "timescar-ask-cancel-next24h-0800",
}
DRY_RUN_JOBS = {
    "timescar-book-sat-3weeks",
    "timescar-extend-sun-3weeks",
}


@dataclass
class TestResult:
    name: str
    source: str
    status: str
    mode: str
    detail: str
    returncode: int | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""


def run(command: list[str], *, timeout: int = 30, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=env,
    )


def json_from_command(command: list[str]) -> dict[str, Any]:
    proc = run(command)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip()[-1000:])
    data = json.loads(proc.stdout)
    if isinstance(data, list):
        return {"jobs": data}
    if not isinstance(data, dict):
        raise RuntimeError("command returned non-object JSON")
    return data


def official_jobs() -> list[dict[str, Any]]:
    data = json_from_command(["openclaw", "cron", "list", "--json"])
    jobs = data.get("jobs") or data.get("items") or data.get("data") or []
    return [item for item in jobs if isinstance(item, dict)]


def load_policy(path: Path) -> tuple[set[str], set[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    owner = {str(item) for item in data.get("owner_discord_dm_channel_ids", [])}
    public = {str(item) for item in data.get("public_discord_channel_ids", [])}
    if data.get("test_delivery_policy") != "owner_dm_only" or data.get("public_test_delivery_forbidden") is not True:
        raise RuntimeError("private test delivery policy is not active")
    if not owner or owner & public:
        raise RuntimeError("owner and public channel policy is invalid")
    return owner, public


def direct_cron_entries(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not path.is_file():
        return entries
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            entries.append({"name": "unknown", "line": line, "parse_error": str(exc)})
            continue
        if "--name" not in tokens or "--command" not in tokens:
            continue
        name_pos = tokens.index("--name")
        channel_pos = tokens.index("--channel-id") if "--channel-id" in tokens else -1
        command_pos = tokens.index("--command")
        entries.append(
            {
                "name": tokens[name_pos + 1],
                "channel_id": tokens[channel_pos + 1] if channel_pos >= 0 else "",
                "command": tokens[command_pos + 1 :],
                "run_as_openclaw": "--run-as-openclaw" in tokens[:command_pos],
                "schedule": " ".join(tokens[:5]),
                "line": line,
            }
        )
    return entries


def job_name(job: dict[str, Any]) -> str:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    return str(job.get("name") or payload.get("name") or job.get("id") or "unknown")


def delivery_target(job: dict[str, Any]) -> str:
    delivery = job.get("delivery") if isinstance(job.get("delivery"), dict) else {}
    return str(delivery.get("to") or "")


def validate_catalog(jobs: list[dict[str, Any]], public_channels: set[str]) -> list[TestResult]:
    results: list[TestResult] = []
    for job in jobs:
        name = job_name(job)
        target = delivery_target(job)
        status = "pass"
        detail = "formal cron contract loaded"
        if name.startswith("timescar-") and target and target != OWNER_DM:
            status, detail = "fail", f"TimesCar delivery drift: {target}"
        if target in public_channels:
            detail += "; formal target is public and will be overridden by the isolated test runner"
        results.append(TestResult(name, "openclaw_cron", status, "contract", detail))
    return results


def isolated_command(name: str, command: list[str]) -> tuple[list[str] | None, str]:
    if name.startswith("news-digest-"):
        repo = Path("/var/lib/openclaw/repos/SpringMonkey")
        return [
            "python3",
            str(repo / "scripts" / "news" / "run_news_pipeline.py"),
            "--job",
            name,
            "--broadcast-mode",
            "test",
            "--no-record-recent",
        ], "full generation with test broadcast mode and no published-state update"
    if name in DRY_RUN_JOBS:
        safe = list(command)
        if "--dry-run" not in safe:
            safe.append("--dry-run")
        return safe, "business flow through confirmation page with submit disabled"
    if name in READ_ONLY_JOBS:
        return list(command), "read-only business flow with delivery removed"
    return None, "no registered isolated test contract"


def read_env_file(path: Path = DEFAULT_ENV_FILE) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def test_direct_entry(entry: dict[str, Any], public_channels: set[str], *, execute: bool, timeout: int) -> TestResult:
    name = str(entry.get("name") or "unknown")
    if entry.get("parse_error"):
        return TestResult(name, "direct_cron", "fail", "parse", str(entry["parse_error"]))
    channel = str(entry.get("channel_id") or "")
    if channel and channel not in ({OWNER_DM} | public_channels):
        return TestResult(name, "direct_cron", "fail", "policy", f"unrecognized delivery channel: {channel}")
    command, detail = isolated_command(name, list(entry.get("command") or []))
    if command is None:
        return TestResult(name, "direct_cron", "blocked", "contract_only", detail)
    if not execute:
        return TestResult(name, "direct_cron", "pass", "plan", detail)
    env = dict(os.environ)
    env.update(read_env_file())
    env.update(
        {
            "HOME": "/var/lib/openclaw",
            "OPENCLAW_CRON_TEST_MODE": "1",
            "OPENCLAW_TEST_DELIVERY_CHANNEL_ID": OWNER_DM,
            "OPENCLAW_PUBLIC_DELIVERY_FORBIDDEN": "1",
        }
    )
    if entry.get("run_as_openclaw") and hasattr(os, "geteuid") and os.geteuid() == 0:
        command = ["runuser", "-u", "openclaw", "--", "env", "HOME=/var/lib/openclaw", *command]
    try:
        proc = run(command, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as exc:
        return TestResult(name, "direct_cron", "fail", "isolated", f"timeout after {timeout}s", stderr_tail=str(exc)[-1500:])
    return TestResult(
        name,
        "direct_cron",
        "pass" if proc.returncode == 0 else "fail",
        "isolated",
        detail,
        proc.returncode,
        (proc.stdout or "").strip()[-3000:],
        (proc.stderr or "").strip()[-3000:],
    )


def systemd_timer_results() -> list[TestResult]:
    try:
        proc = run(
            ["systemctl", "list-timers", "--all", "--no-legend", "--no-pager"],
            timeout=30,
        )
    except Exception as exc:
        return [TestResult("systemd-timers", "systemd", "blocked", "inventory", str(exc))]
    if proc.returncode != 0:
        return [TestResult("systemd-timers", "systemd", "blocked", "inventory", (proc.stderr or proc.stdout)[-1000:])]
    results: list[TestResult] = []
    for line in proc.stdout.splitlines():
        if "openclaw" not in line.lower():
            continue
        timer = next((part for part in line.split() if part.endswith(".timer")), "unknown.timer")
        check = run(["systemctl", "is-enabled", timer], timeout=15)
        results.append(
            TestResult(
                timer,
                "systemd_timer",
                "pass" if check.returncode == 0 else "fail",
                "health",
                (check.stdout or check.stderr).strip() or "timer state checked",
                check.returncode,
            )
        )
    return results


def summarize(results: list[TestResult]) -> dict[str, int]:
    counts = {"pass": 0, "fail": 0, "blocked": 0}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return counts


def render_private_summary(payload: dict[str, Any]) -> str:
    counts = payload["summary"]
    lines = [
        "OpenClaw 私有定时任务测试完成",
        f"通过：{counts.get('pass', 0)}",
        f"失败：{counts.get('fail', 0)}",
        f"阻塞：{counts.get('blocked', 0)}",
        "测试投递：仅 owner 私聊 1497009159940608020",
        "公共频道投递：0",
    ]
    for result in payload["results"]:
        lines.append(f"{result['status'].upper()} | {result['name']} | {result['mode']} | {result['detail'][:180]}")
    return "\n".join(lines)


def deliver_owner_dm(text: str) -> None:
    scripts = Path("/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw")
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from discord_media_delivery import send_discord_message

    send_discord_message(OWNER_DM, text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely test every discovered OpenClaw scheduled job.")
    parser.add_argument("--execute", action="store_true", help="Run registered isolated test commands.")
    parser.add_argument("--deliver-owner-dm", action="store_true", help="Send summary only to the configured owner DM.")
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--direct-cron", type=Path, default=DEFAULT_DIRECT_CRON)
    parser.add_argument("--migration-config", type=Path, default=DEFAULT_MIGRATION_CONFIG)
    args = parser.parse_args()

    owner_channels, public_channels = load_policy(args.migration_config)
    if OWNER_DM not in owner_channels or OWNER_DM in public_channels or PUBLIC_CHANNELS - public_channels:
        raise SystemExit("configured Discord privacy boundary does not match the approved owner/public channels")

    results: list[TestResult] = []
    inventory_error = ""
    try:
        jobs = official_jobs()
        results.extend(validate_catalog(jobs, public_channels))
    except Exception as exc:
        inventory_error = f"official cron inventory failed: {type(exc).__name__}: {exc}"
        results.append(TestResult("openclaw-cron-inventory", "openclaw_cron", "blocked", "inventory", inventory_error))

    entries = direct_cron_entries(args.direct_cron)
    if not entries:
        results.append(TestResult("direct-cron-inventory", "direct_cron", "blocked", "inventory", "direct cron file missing or empty"))
    for entry in entries:
        results.append(test_direct_entry(entry, public_channels, execute=args.execute, timeout=args.timeout))
    results.extend(systemd_timer_results())

    payload = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "execute": args.execute,
        "delivery_policy": "owner_dm_only",
        "owner_dm": OWNER_DM,
        "public_channels_forbidden": sorted(public_channels),
        "formal_cron_modified": False,
        "summary": summarize(results),
        "inventory_error": inventory_error,
        "results": [asdict(item) for item in results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    private_summary = render_private_summary(payload)
    print(private_summary)
    if args.deliver_owner_dm:
        deliver_owner_dm(private_summary)
    return 1 if payload["summary"].get("fail") else 0


if __name__ == "__main__":
    raise SystemExit(main())
