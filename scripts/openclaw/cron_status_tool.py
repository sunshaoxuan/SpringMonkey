#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_JOBS_PATH = Path("/var/lib/openclaw/.openclaw/cron/jobs.json")
DEFAULT_DIRECT_CRON_PATH = Path("/etc/cron.d/openclaw-direct-discord")
DEFAULT_DIRECT_CRON_LOG_DIR = Path("/var/lib/openclaw/.openclaw/logs/direct_discord_cron")
DEFAULT_SYSTEM_LOG_PATHS = (Path("/var/log/syslog"), Path("/var/log/cron"), Path("/var/log/messages"))

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


def has_unescaped_cron_percent(line: str) -> bool:
    escaped = False
    for char in line:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "%":
            return True
    return False


def parse_dt(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def effective_now(message_timestamp: str) -> datetime:
    return parse_dt(message_timestamp) or datetime.now(timezone.utc)


def load_direct_execution_log(name: str, log_dir: Path) -> dict[str, Any] | None:
    path = log_dir / f"{name}.latest.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_recent_system_cron_evidence(name: str, paths: tuple[Path, ...] = DEFAULT_SYSTEM_LOG_PATHS, *, limit: int = 5) -> list[str]:
    if not name:
        return []
    hits: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if name in line and "CRON" in line and "CMD" in line:
                hits.append(line.strip())
    return hits[-limit:]


def summarize_system_cron_evidence(name: str, system_log_paths: tuple[Path, ...]) -> list[str]:
    hits = load_recent_system_cron_evidence(name, system_log_paths)
    if not hits:
        return []
    latest = hits[-1]
    lines = [f"系统 cron 最近触发：{latest[:260]}"]
    if 'DIR=$(printf "' in latest or "$(printf " in latest and "final_broadcast.md" not in latest:
        lines.append("根因证据：系统 cron 日志显示命令在 printf/% 附近被截断；cron 文件中的未转义 % 会造成这种截断。")
    return lines


def summarize_direct_execution(name: str, log_dir: Path, now: datetime) -> list[str]:
    data = load_direct_execution_log(name, log_dir)
    if not data:
        return ["最近执行：未找到 direct cron 最新执行记录。"]
    started_raw = str(data.get("started") or "")
    finished_raw = str(data.get("finished") or "")
    started = parse_dt(started_raw)
    finished = parse_dt(finished_raw)
    returncode = data.get("returncode", "未知")
    delivery = str(data.get("delivery") or "unknown")
    channel = str(data.get("channel_id") or data.get("channel") or "unknown")
    if channel == "unknown":
        command = data.get("command")
        if isinstance(command, list):
            for index, item in enumerate(command):
                if item == "--channel-id" and index + 1 < len(command):
                    channel = str(command[index + 1])
                    break
    same_day = bool(started and started.astimezone(now.tzinfo).date() == now.date())
    status = "成功" if returncode == 0 else f"失败/异常（returncode={returncode}）"
    lines = [
        f"最近执行：{status}",
        f"开始：{started_raw or '未知'}",
        f"结束：{finished_raw or '未知'}",
        f"今天是否执行过：{'是' if same_day else '否'}",
        f"投递：{delivery}",
    ]
    if channel != "unknown":
        lines.append(f"投递频道：{channel}")
    published = data.get("publishedMark")
    if published:
        lines.append(f"发布标记：{published}")
    stderr = str(data.get("stderr") or "").strip()
    stdout = str(data.get("stdout") or "").strip()
    if returncode != 0:
        evidence = (stderr or stdout)[-300:].replace("\n", " ")
        if evidence:
            lines.append(f"失败证据：{evidence}")
    return lines


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


def summarize_job(
    job: dict[str, Any],
    direct_lines: list[str],
    log_dir: Path,
    now: datetime,
    system_log_paths: tuple[Path, ...],
) -> list[str]:
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
    lines = [
        f"任务：{name} | 内部：{'enabled' if enabled else 'disabled'} | 直发：{direct_status}{direct_detail}",
        f"ID：{job.get('id') or payload.get('id') or '未知'}",
        f"内部计划：{job.get('cron') or job.get('schedule') or payload.get('cron') or payload.get('schedule') or '未知'}",
        f"模型：{payload.get('model') or job.get('model') or '未知'}",
    ]
    if direct:
        if has_unescaped_cron_percent(direct[0]):
            lines.append("配置风险：direct cron 命令包含未转义 %；cron 会从该处截断命令，导致定时触发但脚本不完整。")
        lines.extend(summarize_system_cron_evidence(name, system_log_paths))
        lines.extend(summarize_direct_execution(name, log_dir, now))
    return lines


def format_status(
    text: str,
    topic: str,
    jobs_path: Path,
    direct_cron_path: Path = DEFAULT_DIRECT_CRON_PATH,
    *,
    log_dir: Path = DEFAULT_DIRECT_CRON_LOG_DIR,
    message_timestamp: str = "",
    system_log_paths: tuple[Path, ...] = DEFAULT_SYSTEM_LOG_PATHS,
) -> str:
    jobs = load_jobs(jobs_path)
    direct_lines = load_direct_cron_lines(direct_cron_path)
    matches = [job for job in jobs if matches_topic(job, topic)]
    direct_match_count = sum(
        1
        for job in matches
        if direct_cron_for_job(str(job.get("name") or (job.get("payload") or {}).get("name") or job.get("id") or ""), direct_lines)
    )
    cron_percent_risks = [
        name
        for name in [str(job.get("name") or (job.get("payload") or {}).get("name") or job.get("id") or "") for job in matches]
        for line in direct_cron_for_job(name, direct_lines)
        if has_unescaped_cron_percent(line)
    ]
    historical_truncation_risks = [
        name
        for name in [str(job.get("name") or (job.get("payload") or {}).get("name") or job.get("id") or "") for job in matches]
        if any("根因证据：" in line for line in summarize_system_cron_evidence(name, system_log_paths))
    ]
    now = effective_now(message_timestamp)
    names = [str(job.get("name") or (job.get("payload") or {}).get("name") or job.get("id") or "") for job in matches]
    executions = [load_direct_execution_log(name, log_dir) for name in names if name]
    today_runs = [
        item
        for item in executions
        if item and (started := parse_dt(str(item.get("started") or ""))) and started.astimezone(now.tzinfo).date() == now.date()
    ]
    today_success = [item for item in today_runs if item and item.get("returncode") == 0 and str(item.get("delivery") or "") == "delivered"]
    today_failures = [item for item in today_runs if item and item.get("returncode") != 0]
    if cron_percent_risks:
        conclusion = f"匹配任务 {len(matches)} 个；直发 cron 启用 {direct_match_count} 个；发现 {len(cron_percent_risks)} 个 direct cron 命令截断风险，这是未投递的优先原因。"
    elif historical_truncation_risks:
        conclusion = f"匹配任务 {len(matches)} 个；直发 cron 启用 {direct_match_count} 个；系统日志显示 {len(historical_truncation_risks)} 个任务最近被 cron 命令截断，这是未投递的优先原因。"
    elif matches and direct_match_count and today_success:
        conclusion = f"匹配任务 {len(matches)} 个；直发 cron 启用 {direct_match_count} 个；今天已有 {len(today_success)} 个成功投递记录。"
    elif matches and direct_match_count and today_runs:
        conclusion = f"匹配任务 {len(matches)} 个；直发 cron 启用 {direct_match_count} 个；今天有执行记录但未确认成功投递。"
    elif matches and direct_match_count:
        conclusion = f"匹配任务 {len(matches)} 个；直发 cron 启用 {direct_match_count} 个；今天未找到 direct cron 成功投递记录。"
    else:
        conclusion = f"匹配任务 {len(matches)} 个；直发 cron 启用 {direct_match_count} 个。内部 disabled 不一定代表停发，以直发 cron 为实际公共投递计划。"
    lines = [
        "OpenClaw 定时任务状态",
        f"主题：{topic}",
        f"任务总数：{len(jobs)}",
        f"匹配数量：{len(matches)}",
        f"结论：{conclusion}",
    ]
    if today_failures:
        lines.append(f"今天失败记录：{len(today_failures)} 个。")
    if not matches:
        lines.append("状态：未找到匹配的正式定时任务。")
        return "\n".join(lines)
    for index, job in enumerate(matches[:10], start=1):
        lines.append("")
        lines.append(f"{index}.")
        lines.extend(summarize_job(job, direct_lines, log_dir, now, system_log_paths))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only OpenClaw cron status helper.")
    parser.add_argument("--text", default="")
    parser.add_argument("--message-timestamp", default="")
    parser.add_argument("--topic", default="xhs")
    parser.add_argument("--jobs-path", type=Path, default=Path(os.environ.get("OPENCLAW_CRON_JOBS_PATH", DEFAULT_JOBS_PATH)))
    parser.add_argument("--direct-cron-path", type=Path, default=Path(os.environ.get("OPENCLAW_DIRECT_CRON_PATH", DEFAULT_DIRECT_CRON_PATH)))
    parser.add_argument("--direct-cron-log-dir", type=Path, default=Path(os.environ.get("OPENCLAW_DIRECT_CRON_LOG_DIR", DEFAULT_DIRECT_CRON_LOG_DIR)))
    parser.add_argument("--system-log-path", action="append", type=Path, default=None)
    args = parser.parse_args()
    system_log_paths = tuple(args.system_log_path) if args.system_log_path else DEFAULT_SYSTEM_LOG_PATHS
    print(
        format_status(
            args.text,
            args.topic,
            args.jobs_path,
            args.direct_cron_path,
            log_dir=args.direct_cron_log_dir,
            message_timestamp=args.message_timestamp,
            system_log_paths=system_log_paths,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
