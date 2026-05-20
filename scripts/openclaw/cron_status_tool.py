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
DEFAULT_DIRECT_CRON_PATH = Path("/etc/cron.d/openclaw-direct-discord")

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

def load_direct_cron_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def direct_cron_for_job(name: str, lines: list[str]) -> list[str]:
    if not name:
        return []
    marker = f"--name {name}"
    return [line for line in lines if marker in line]


def direct_cron_schedule(line: str) -> str:
    parts = line.split()
    if len(parts) >= 5:
        return " ".join(parts[:5])
    return "unknown"


def direct_cron_channel(line: str) -> str:
    parts = line.split()
    for index, item in enumerate(parts):
        if item == "--channel-id" and index + 1 < len(parts):
            return parts[index + 1]
    return "unknown"


def matches_topic(job: dict[str, Any], topic: str) -> bool:
    normalized_topic = (topic or "all").strip().lower()
    if normalized_topic in {"", "all", "any"}:
        return True
    haystack = job_text(job).lower()
    if normalized_topic == "xhs":
        return any(token in haystack for token in ("xhs", "小红书", "小紅書", "xiaohongshu", "文章撰写", "投稿"))
    if normalized_topic == "news":
        return any(token in haystack for token in ("news", "新闻", "新聞", "digest", "broadcast", "播报", "早报", "晚报"))
    if normalized_topic == "weather":
        return any(token in haystack for token in ("weather", "天气", "天氣", "forecast", "预报", "預報"))
    return normalized_topic in haystack


def summarize_job(job: dict[str, Any], direct_lines: list[str]) -> list[str]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    enabled = job.get("enabled")
    if enabled is None:
        enabled = job.get("status") not in {"disabled", "paused", "DISABLED", "PAUSED"}
    name = str(job.get("name") or payload.get("name") or job.get("id") or "未知")
    direct = direct_cron_for_job(name, direct_lines)
    direct_status = "enabled" if direct else "not_found"
    direct_detail = ""
    if direct:
        direct_detail = f" | 直发计划：{direct_cron_schedule(direct[0])} | 频道：{direct_cron_channel(direct[0])}"
    return [
        f"任务：{name} | 内部：{'enabled' if enabled else 'disabled'} | 直发：{direct_status}{direct_detail}",
        f"ID：{job.get('id') or payload.get('id') or '未知'}",
        f"内部计划：{job.get('cron') or job.get('schedule') or payload.get('cron') or payload.get('schedule') or '未知'}",
        f"模型：{payload.get('model') or job.get('model') or '未知'}",
    ]


def format_status(text: str, topic: str, jobs_path: Path, direct_cron_path: Path = DEFAULT_DIRECT_CRON_PATH) -> str:
    jobs = load_jobs(jobs_path)
    direct_lines = load_direct_cron_lines(direct_cron_path)
    matches = [job for job in jobs if matches_topic(job, topic)]
    direct_match_count = sum(
        1
        for job in matches
        if direct_cron_for_job(str(job.get("name") or (job.get("payload") or {}).get("name") or job.get("id") or ""), direct_lines)
    )
    lines = [
        "OpenClaw 定时任务状态",
        f"主题：{topic}",
        f"任务总数：{len(jobs)}",
        f"匹配数量：{len(matches)}",
        f"结论：匹配任务 {len(matches)} 个；直发 cron 启用 {direct_match_count} 个。内部 disabled 不一定代表停发，以直发 cron 为实际公共投递计划。",
    ]
    if not matches:
        lines.append("状态：未找到匹配的正式定时任务。")
        return "\n".join(lines)
    for index, job in enumerate(matches[:10], start=1):
        lines.append("")
        lines.append(f"{index}.")
        lines.extend(summarize_job(job, direct_lines))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only OpenClaw cron status helper.")
    parser.add_argument("--text", default="")
    parser.add_argument("--message-timestamp", default="")
    parser.add_argument("--topic", default="xhs")
    parser.add_argument("--jobs-path", type=Path, default=Path(os.environ.get("OPENCLAW_CRON_JOBS_PATH", DEFAULT_JOBS_PATH)))
    parser.add_argument("--direct-cron-path", type=Path, default=Path(os.environ.get("OPENCLAW_DIRECT_CRON_PATH", DEFAULT_DIRECT_CRON_PATH)))
    args = parser.parse_args()
    print(format_status(args.text, args.topic, args.jobs_path, args.direct_cron_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
