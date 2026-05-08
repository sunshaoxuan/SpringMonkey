#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_JOBS_PATH = Path("/var/lib/openclaw/.openclaw/cron/jobs.json")

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def load_jobs(path: Path) -> list[dict[str, Any]]:
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            jobs = data.get("jobs")
            if isinstance(jobs, list):
                return [item for item in jobs if isinstance(item, dict)]
    try:
        proc = subprocess.run(
            ["openclaw", "cron", "list", "--json"],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except Exception:
        return []
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        jobs = data.get("jobs") or data.get("items") or data.get("data")
        if isinstance(jobs, list):
            return [item for item in jobs if isinstance(item, dict)]
    return []


def job_text(job: dict[str, Any]) -> str:
    fields = [
        job.get("name"),
        job.get("id"),
        job.get("description"),
        job.get("prompt"),
        job.get("cron"),
        job.get("schedule"),
    ]
    payload = job.get("payload")
    if isinstance(payload, dict):
        fields.extend([payload.get("prompt"), payload.get("name"), payload.get("model")])
    return " ".join(str(item or "") for item in fields)


def matches_topic(job: dict[str, Any], topic: str) -> bool:
    haystack = job_text(job).lower()
    if topic == "xhs":
        return any(token in haystack for token in ("xhs", "小红书", "小紅書", "xiaohongshu", "文章撰写", "投稿"))
    return topic.lower() in haystack


def summarize_job(job: dict[str, Any]) -> list[str]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    enabled = job.get("enabled")
    if enabled is None:
        enabled = job.get("status") not in {"disabled", "paused", "DISABLED", "PAUSED"}
    return [
        f"任务：{job.get('name') or payload.get('name') or job.get('id') or '未知'}",
        f"ID：{job.get('id') or payload.get('id') or '未知'}",
        f"状态：{'enabled' if enabled else 'disabled'}",
        f"计划：{job.get('cron') or job.get('schedule') or payload.get('cron') or payload.get('schedule') or '未知'}",
        f"模型：{payload.get('model') or job.get('model') or '未知'}",
    ]


def format_status(text: str, topic: str, jobs_path: Path) -> str:
    jobs = load_jobs(jobs_path)
    matches = [job for job in jobs if matches_topic(job, topic)]
    lines = [
        "OpenClaw 定时任务状态",
        f"主题：{topic}",
        f"任务总数：{len(jobs)}",
        f"匹配数量：{len(matches)}",
    ]
    if not matches:
        lines.append("状态：未找到匹配的正式定时任务。")
        return "\n".join(lines)
    for index, job in enumerate(matches[:10], start=1):
        lines.append("")
        lines.append(f"{index}.")
        lines.extend(summarize_job(job))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only OpenClaw cron status helper.")
    parser.add_argument("--text", default="")
    parser.add_argument("--message-timestamp", default="")
    parser.add_argument("--topic", default="xhs")
    parser.add_argument("--jobs-path", type=Path, default=Path(os.environ.get("OPENCLAW_CRON_JOBS_PATH", DEFAULT_JOBS_PATH)))
    args = parser.parse_args()
    print(format_status(args.text, args.topic, args.jobs_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
