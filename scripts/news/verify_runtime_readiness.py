#!/usr/bin/env python3
"""
宿主机就绪检查：broadcast 与 jobs.json 的 pipeline 一致、可选 DNS/记忆文件告警。
用于上线门禁；失败时非零退出（仅 pipeline 契约失败为硬错误）。
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "news" / "broadcast.json"
DEFAULT_JOBS = Path("/var/lib/openclaw/.openclaw/cron/jobs.json")
JST = timezone(timedelta(hours=9))


def today_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def load_json(p: Path) -> dict:
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="新闻任务域运行时就绪检查")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--jobs", type=Path, default=DEFAULT_JOBS)
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=Path("/var/lib/openclaw/.openclaw/workspace"),
    )
    parser.add_argument(
        "--strict-dns",
        action="store_true",
        help="feeds.reuters.com 不可解析时退出 2",
    )
    args = parser.parse_args()

    cfg = load_json(args.config)
    nex = cfg.get("newsExecution") or {}
    pipeline = nex.get("mode") == "pipeline"
    warnings: list[str] = []
    errors: list[str] = []

    if not args.jobs.is_file():
        print(f"WARN: jobs.json 不存在，跳过契约检查: {args.jobs}", file=sys.stderr)
    elif pipeline:
        jobs_doc = load_json(args.jobs)
        jobs_by_name = {j.get("name"): j for j in jobs_doc.get("jobs", [])}
        token = "【新闻定时任务 · 流水线模式】"
        for spec in cfg.get("jobs", []):
            name = spec["name"]
            job = jobs_by_name.get(name)
            if not job:
                errors.append(f"job missing in jobs.json: {name}")
                continue
            msg = job.get("payload", {}).get("message", "")
            if token not in msg:
                errors.append(f"{name}: payload 未含流水线标记（请 apply_news_config + 重启网关）")
        exp_timeout = int(
            nex.get("cronTimeoutSeconds")
            or max(int(cfg.get("model", {}).get("timeoutSeconds") or 3600), 7200)
        )
        for spec in cfg.get("jobs", []):
            job = jobs_by_name.get(spec["name"])
            if not job:
                continue
            ts = int(job.get("payload", {}).get("timeoutSeconds") or 0)
            if ts != exp_timeout:
                errors.append(
                    f"{spec['name']}: timeoutSeconds={ts} 期望 {exp_timeout}（请重新 apply）"
                )
    else:
        print("INFO: newsExecution.mode 非 pipeline，跳过流水线契约检查")

    # DNS（采集常用）
    try:
        socket.getaddrinfo("feeds.reuters.com", 443, type=socket.SOCK_STREAM)
    except OSError as e:
        line = f"DNS: feeds.reuters.com 不可解析 ({e})，Reuters 经典 RSS 将失败"
        if args.strict_dns:
            errors.append(line)
        else:
            warnings.append(line)

    mem = args.workspace_root / "memory" / f"{today_jst()}.md"
    if not mem.is_file():
        warnings.append(f"当日 memory 缺失: {mem}（可运行 ensure_daily_memory.py）")

    for w in warnings:
        print(f"WARN {w}", file=sys.stderr)
    for e in errors:
        print(f"FAIL {e}", file=sys.stderr)

    if errors:
        print("RUNTIME_VERIFY_FAIL", file=sys.stderr)
        return 1
    print("RUNTIME_VERIFY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
