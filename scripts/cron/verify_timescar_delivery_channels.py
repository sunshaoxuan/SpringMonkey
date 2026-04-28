#!/usr/bin/env python3
"""
Fail if any OpenClaw cron job whose name starts with ``timescar-`` delivers to
the public news/weather Discord channel instead of the private DM channel.

This catches copy-paste or ``openclaw cron edit --to`` mistakes that leak
rental/personal TimesCar output to a public channel.

Usage (from dev machine with a pulled ``jobs.json``):

  python3 scripts/cron/verify_timescar_delivery_channels.py /path/to/jobs.json

Usage (on host, example):

  python3 -c "import json,sys;print(json.dumps(json.load(open('/var/lib/openclaw/.openclaw/cron/jobs.json'))))" \\
    | python3 scripts/cron/verify_timescar_delivery_channels.py -

Exit codes: 0 ok, 1 violation, 2 usage/IO error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Must match docs/ops/CRON_TASKS_SUMMARY.md
DISCORD_PUBLIC = "1483636573235843072"
DISCORD_TIMESCAR_PRIVATE = "1497009159940608020"


def load_payload(path: str | None) -> dict:
    if not path or path == "-":
        return json.load(sys.stdin)
    p = Path(path)
    if not p.is_file():
        print(f"MISSING_FILE: {p}", file=sys.stderr)
        raise SystemExit(2)
    raw = p.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")
    return json.loads(text)


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify TimesCar cron jobs target private Discord only.")
    ap.add_argument(
        "jobs_json",
        nargs="?",
        help="Path to OpenClaw cron jobs.json, or '-' for stdin",
    )
    args = ap.parse_args()
    if args.jobs_json is None:
        ap.print_help()
        return 2

    try:
        data = load_payload(args.jobs_json)
    except (json.JSONDecodeError, OSError) as e:
        print(f"READ_ERROR: {e}", file=sys.stderr)
        return 2

    jobs = data.get("jobs")
    if not isinstance(jobs, list):
        print("INVALID: root jobs missing", file=sys.stderr)
        return 2

    bad: list[tuple[str, str, str]] = []
    for job in jobs:
        name = job.get("name") or ""
        if not name.startswith("timescar-"):
            continue
        delivery = job.get("delivery") or {}
        to_id = str(delivery.get("to") or "").strip()
        if to_id == DISCORD_PUBLIC:
            bad.append((name, job.get("id", "?"), to_id))
        elif to_id and to_id != DISCORD_TIMESCAR_PRIVATE:
            bad.append((name, job.get("id", "?"), to_id))

    if bad:
        print("TIMESCAR_DELIVERY_VIOLATION", file=sys.stderr)
        print(
            "TimesCar jobs must use Discord channel "
            f"{DISCORD_TIMESCAR_PRIVATE} (private), never public {DISCORD_PUBLIC}.",
            file=sys.stderr,
        )
        for name, jid, to_id in bad:
            print(f"  job={name} id={jid} delivery.to={to_id}", file=sys.stderr)
        print(
            "\nFix example (host):\n"
            "  HOME=/var/lib/openclaw openclaw cron edit <jobId> "
            f"--to {DISCORD_TIMESCAR_PRIVATE} --announce\n",
            file=sys.stderr,
        )
        return 1

    ts = [j for j in jobs if str(j.get("name", "")).startswith("timescar-")]
    print(f"TIMESCAR_DELIVERY_OK {len(ts)} jobs -> {DISCORD_TIMESCAR_PRIVATE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())