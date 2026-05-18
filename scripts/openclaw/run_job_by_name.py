#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

REPO = Path(os.environ.get("SPRINGMONKEY_REPO", Path(__file__).resolve().parents[2]))
JOBS_PATH = Path(os.environ.get("OPENCLAW_CRON_JOBS_PATH", "/var/lib/openclaw/.openclaw/cron/jobs.json"))
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from discord_media_delivery import parse_media_reply, send_discord_message


DIRECT_SCRIPT_JOBS: dict[str, list[str]] = {
    "weather-report-jst-0700": [
        "python3",
        str(REPO / "scripts" / "weather" / "weather_image_forecast.py"),
    ],
    "news-digest-jst-0900": [
        "bash",
        "-lc",
        (
            "set -e; "
            f"OUT=$(python3 {shlex.quote(str(REPO / 'scripts' / 'news' / 'jobs' / 'news_digest_jst_0900.py'))}); "
            'DIR=$(printf "%s\\n" "$OUT" | sed -n "s/^PIPELINE_OK //p" | tail -n1); '
            'test -n "$DIR"; cat "$DIR/final_broadcast.md"'
        ),
    ],
    "news-digest-jst-1700": [
        "bash",
        "-lc",
        (
            "set -e; "
            f"OUT=$(python3 {shlex.quote(str(REPO / 'scripts' / 'news' / 'jobs' / 'news_digest_jst_1700.py'))}); "
            'DIR=$(printf "%s\\n" "$OUT" | sed -n "s/^PIPELINE_OK //p" | tail -n1); '
            'test -n "$DIR"; cat "$DIR/final_broadcast.md"'
        ),
    ],
}

def find_id_by_name(name: str) -> str | None:
    if not JOBS_PATH.exists():
        return None
    with open(JOBS_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
        for job in data.get('jobs', []):
            if job.get('name') == name:
                return job.get('id')
    return None


def run_direct_script_job(name: str) -> int:
    """Run script-like jobs directly for manual owner-triggered execution.

    Scheduled public delivery is handled by /etc/cron.d/openclaw-direct-discord.
    Manual Harness invocations must not call `openclaw cron run` for these jobs,
    because that re-enters an agent turn and can publish model/tool errors to the
    job's configured public destination.
    """
    command = DIRECT_SCRIPT_JOBS[name]
    proc = subprocess.run(
        command,
        cwd=REPO,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=int(os.environ.get("OPENCLAW_RUN_JOB_TIMEOUT", "5400")),
    )
    if proc.returncode == 0:
        final_report = (proc.stdout or "").strip()
        delivery = "manual_owner_reply"
        reply_channel = os.environ.get("OPENCLAW_REPLY_CHANNEL_ID", "").strip()
        media_delivery = ""
        if reply_channel and parse_media_reply(final_report):
            _chunks, media_delivery = send_discord_message(reply_channel, final_report)
            delivery = "manual_media_sent"
            final_report = "天气预报图片已发送。"
        print(
            json.dumps(
                {
                    "status": "success",
                    "job_name": name,
                    "delivery": delivery,
                    "final_report": final_report,
                    "media_delivery": media_delivery,
                    "stderr_hidden": bool((proc.stderr or "").strip()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print(
        json.dumps(
            {
                "status": "failed",
                "job_name": name,
                "delivery": "manual_owner_reply",
                "returncode": proc.returncode,
                "stdout": (proc.stdout or "").strip()[-1200:],
                "stderr": (proc.stderr or "").strip()[-1200:],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return proc.returncode or 1


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: run_job_by_name.py <job_name>")
        return 1

    name = sys.argv[1]
    if name in DIRECT_SCRIPT_JOBS and os.environ.get("OPENCLAW_RUN_JOB_FORCE_OPENCLAW_CRON") != "1":
        return run_direct_script_job(name)

    job_id = find_id_by_name(name)
    
    if not job_id:
        print(f"Error: Unknown cron job name: {name}")
        return 1

    print(f"Resolved '{name}' to ID '{job_id}'. Running...")
    
    cmd = ["openclaw", "cron", "run", job_id]
    
    # Set HOME if needed
    os.environ["HOME"] = "/var/lib/openclaw"
    
    if os.geteuid() == 0:
        cmd = ["runuser", "-u", "openclaw", "--", "env", "HOME=/var/lib/openclaw", "openclaw", "cron", "run", job_id]
        
    proc = subprocess.run(cmd)
    return proc.returncode

if __name__ == "__main__":
    raise SystemExit(main())
