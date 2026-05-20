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
COMPOSITE_SCRIPT_JOBS: dict[str, list[str]] = {
    "news-digest-jst-today": ["news-digest-jst-0900", "news-digest-jst-1700"],
}


def is_news_job(name: str) -> bool:
    return name.startswith("news-digest-jst-")


def run_news_pipeline_job(name: str) -> tuple[int, str, str, str]:
    script = REPO / "scripts" / "news" / "run_news_pipeline.py"
    cmd = [sys.executable, str(script), "--job", name]
    start_ts = os.environ.get("OPENCLAW_NEWS_WINDOW_START_TS", "").strip()
    end_ts = os.environ.get("OPENCLAW_NEWS_WINDOW_END_TS", "").strip()
    if start_ts and end_ts:
        cmd.extend(
            [
                "--window-start",
                start_ts,
                "--window-end",
                end_ts,
                "--reset-published-window-start",
                start_ts,
                "--reset-published-window-end",
                end_ts,
                "--ignore-recent",
            ]
        )
    proc = subprocess.run(
        cmd,
        cwd=REPO,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=int(os.environ.get("OPENCLAW_RUN_JOB_TIMEOUT", "5400")),
    )
    run_dir = ""
    for line in (proc.stdout or "").splitlines():
        if line.startswith("PIPELINE_OK "):
            run_dir = line.split(None, 1)[1].strip()
    final_report = ""
    if run_dir:
        final_path = Path(run_dir) / "final_broadcast.md"
        if final_path.is_file():
            final_report = final_path.read_text(encoding="utf-8", errors="replace").strip()
    return proc.returncode, final_report, run_dir, proc.stderr or proc.stdout or ""


def mark_news_published(name: str, run_dir: str) -> str:
    if not run_dir:
        return "no-run-dir"
    script = REPO / "scripts" / "news" / "run_news_pipeline.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--job", name, "--mark-published-run-dir", run_dir],
        cwd=REPO,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    if proc.returncode != 0:
        return f"failed:{proc.returncode}:{(proc.stderr or proc.stdout)[-300:]}"
    return (proc.stdout or "").strip() or "marked"


def maybe_deliver_news(name: str, final_report: str, run_dir: str) -> tuple[str, str]:
    channel = os.environ.get("OPENCLAW_NEWS_DELIVERY_CHANNEL_ID", "").strip()
    if not channel:
        return "manual_owner_reply", ""
    chunks, kind = send_discord_message(channel, final_report)
    mark = mark_news_published(name, run_dir)
    return f"public_discord:{channel}:chunks={chunks}:kind={kind}", mark

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
    if is_news_job(name):
        returncode, final_report, run_dir, detail = run_news_pipeline_job(name)
        stderr_text = detail
    else:
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
        returncode, final_report, run_dir, stderr_text = proc.returncode, (proc.stdout or "").strip(), "", proc.stderr or ""
    if returncode == 0 and is_news_job(name) and not final_report.strip():
        returncode = 4
        stderr_text = f"news pipeline did not produce final_broadcast.md content; run_dir={run_dir or 'none'}; detail={stderr_text[-500:]}"
    if returncode == 0:
        delivery = "manual_owner_reply"
        reply_channel = os.environ.get("OPENCLAW_REPLY_CHANNEL_ID", "").strip()
        media_delivery = ""
        published_mark = ""
        if is_news_job(name):
            delivery, published_mark = maybe_deliver_news(name, final_report, run_dir)
            if delivery.startswith("public_discord:"):
                final_report = f"{name} 已补发到公共频道。\n投递：{delivery}\n发布标记：{published_mark}"
        elif reply_channel and parse_media_reply(final_report):
            _chunks, media_delivery = send_discord_message(reply_channel, final_report)
            delivery = "manual_media_sent"
            final_report = ""
        print(
            json.dumps(
                {
                    "status": "success",
                    "job_name": name,
                    "delivery": delivery,
                    "final_report": final_report,
                    "media_delivery": media_delivery,
                    "publishedMark": published_mark,
                    "stderr_hidden": bool((stderr_text or "").strip()),
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
                "returncode": returncode,
                "stdout": final_report[-1200:],
                "stderr": (stderr_text or "").strip()[-1200:],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return int(returncode) or 1


def run_composite_script_job(name: str) -> int:
    parts = COMPOSITE_SCRIPT_JOBS[name]
    reports: list[str] = []
    failures: list[dict[str, str | int]] = []
    for part in parts:
        returncode, final_report, run_dir, detail = run_news_pipeline_job(part)
        if returncode == 0 and not final_report.strip():
            failures.append(
                {
                    "job_name": part,
                    "returncode": 4,
                    "stdout": "",
                    "stderr": f"news pipeline did not produce final_broadcast.md content; run_dir={run_dir or 'none'}; detail={(detail or '')[-500:]}",
                }
            )
        elif returncode == 0:
            delivery, published_mark = maybe_deliver_news(part, final_report, run_dir)
            if delivery.startswith("public_discord:"):
                reports.append(f"## {part}\n已补发到公共频道。\n投递：{delivery}\n发布标记：{published_mark}")
            else:
                reports.append(f"## {part}\n{final_report}")
        else:
            failures.append(
                {
                    "job_name": part,
                    "returncode": returncode,
                    "stdout": final_report[-800:],
                    "stderr": (detail or "").strip()[-800:],
                }
            )
    if failures:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "job_name": name,
                    "delivery": "manual_owner_reply",
                    "failures": failures,
                    "final_report": "\n\n".join(reports),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": "success",
                "job_name": name,
                "delivery": "manual_owner_reply",
                "final_report": "\n\n".join(reports),
                "stderr_hidden": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: run_job_by_name.py <job_name>")
        return 1

    name = sys.argv[1]
    if name in COMPOSITE_SCRIPT_JOBS:
        return run_composite_script_job(name)
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
