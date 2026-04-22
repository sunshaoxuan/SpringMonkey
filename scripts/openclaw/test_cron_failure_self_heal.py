#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="cron_failure_self_heal_") as tmp:
        root = Path(tmp) / "kernel"
        root.mkdir(parents=True, exist_ok=True)
        jobs_path = Path(tmp) / "jobs.json"
        journal_path = Path(tmp) / "journal.txt"
        jobs_path.write_text(
            json.dumps(
                {
                    "jobs": [
                        {
                            "name": "timescar-ask-cancel-next24h-0700",
                            "payload": {
                                "message": "Check TimesCar next-24h reservations, ask whether to cancel, and report the blocker if the site fails."
                            },
                            "delivery": {"channel": "line", "to": "Ufed"},
                        }
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        journal_path.write_text(
            "\n".join(
                [
                    '2026-04-23T07:10:00+09:00 host openclaw[1]: Cron job "timescar-ask-cancel-next24h-0700" failed: cron: job execution timed out',
                    '2026-04-23T07:10:10+09:00 host openclaw[1]: Cron job "timescar-ask-cancel-next24h-0700" failed: cron: job execution timed out',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        cmd = [
            sys.executable,
            str(repo_root / "scripts" / "openclaw" / "cron_failure_self_heal.py"),
            "--root",
            str(root),
            "--repo-root",
            str(repo_root),
            "--jobs-file",
            str(jobs_path),
            "--journal-file",
            str(journal_path),
        ]
        first = subprocess.run(cmd, capture_output=True, text=True, check=True)
        payload = json.loads(first.stdout)
        if payload["processed_count"] != 1:
            raise AssertionError(f"expected one processed cron failure, got {payload['processed_count']}")
        item = payload["processed"][0]
        if item["gap_category"] != "runtime_timeout":
            raise AssertionError(f"expected runtime_timeout cron gap, got {item['gap_category']}")
        if item["channel"] != "cron:line":
            raise AssertionError(f"expected cron:line channel, got {item['channel']}")
        if not item.get("helper") or item["helper"]["status"] != "promoted":
            raise AssertionError(f"expected promoted helper payload, got {item.get('helper')}")

        second = subprocess.run(cmd, capture_output=True, text=True, check=True)
        second_payload = json.loads(second.stdout)
        if second_payload["processed_count"] != 0:
            raise AssertionError(f"expected deduped second run, got {second_payload['processed_count']}")

        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
