#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    script = Path(__file__).with_name("migrate_existing_cron_to_orchestrator.py")
    with tempfile.TemporaryDirectory(prefix="cron_migrate_orchestrator_") as tmp:
        jobs_file = Path(tmp) / "jobs.json"
        jobs_file.write_text(
            json.dumps(
                {
                    "jobs": [
                        {
                            "name": "weather-report-jst-0700",
                            "description": "weather",
                            "enabled": True,
                            "schedule": {"expr": "0 7 * * *", "tz": "Asia/Tokyo"},
                            "payload": {
                                "message": "fetch weather, translate, report",
                                "model": "openai-codex/gpt-5.5",
                                "thinking": "low",
                                "timeoutSeconds": 1800,
                                "lightContext": True,
                            },
                            "delivery": {"channel": "discord", "to": "1483636573235843072", "accountId": "default"},
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--jobs-file",
                str(jobs_file),
                "--dry-run",
                "--only",
                "weather-report-jst-0700",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(proc.stdout)
        if data["jobs"][0]["status"] != "would_migrate":
            raise AssertionError(f"expected dry-run migration, got {data}")
        print("migrate_existing_cron_to_orchestrator_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
