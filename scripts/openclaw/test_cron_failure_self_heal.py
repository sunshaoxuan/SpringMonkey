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
        if payload.get("shadow_bridge", {}).get("status") != "captured":
            raise AssertionError(f"expected shadow capture, got {payload.get('shadow_bridge')}")
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

        official_root = Path(tmp) / "official-kernel"
        official_tasks = Path(tmp) / "tasks.json"
        official_tasks.write_text(
            json.dumps(
                {
                    "count": 1,
                    "runtime": "cron",
                    "status": None,
                    "tasks": [
                        {
                            "taskId": "task-official-1",
                            "runtime": "cron",
                            "sourceId": "timescar-ask-cancel-next24h-0700",
                            "label": "timescar-ask-cancel-next24h-0700",
                            "task": "check reservation",
                            "status": "timed_out",
                            "deliveryStatus": "failed",
                            "error": "official cron execution timed out",
                            "endedAt": 1773888000000,
                            "runId": "run-official-1",
                            "parentFlowId": "flow-official-1"
                        }
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        official_cmd = [
            sys.executable,
            str(repo_root / "scripts" / "openclaw" / "cron_failure_self_heal.py"),
            "--root",
            str(official_root),
            "--repo-root",
            str(repo_root),
            "--jobs-file",
            str(jobs_path),
            "--tasks-file",
            str(official_tasks),
            "--source",
            "tasks",
            "--official-max-age-seconds",
            "0",
        ]
        official = subprocess.run(official_cmd, capture_output=True, text=True, check=True)
        official_payload = json.loads(official.stdout)
        if official_payload["signal_source"] != "official_tasks":
            raise AssertionError(f"expected official task signal, got {official_payload['signal_source']}")
        if official_payload.get("shadow_bridge", {}).get("status") != "captured":
            raise AssertionError(f"expected official shadow capture, got {official_payload.get('shadow_bridge')}")
        official_item = official_payload["processed"][0]
        if official_item["official_task_id"] != "task-official-1":
            raise AssertionError(f"official task id missing: {official_item}")
        if official_item["official_flow_id"] != "flow-official-1":
            raise AssertionError(f"official flow id missing: {official_item}")

        print(json.dumps(payload, ensure_ascii=False, indent=2))
        generated_helper = repo_root / "scripts" / "openclaw" / "helpers" / "check_timescar_next_24h_reservat_repair.py"
        if generated_helper.is_file():
            generated_helper.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
