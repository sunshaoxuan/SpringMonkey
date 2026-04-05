#!/usr/bin/env python3
"""
为 OpenClaw 工作区创建当日 memory 文件，避免 agent read ENOENT（如 2026-04-05.md）。
默认按亚洲/东京日期；路径可通过环境变量覆盖。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))


def today_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def main() -> int:
    parser = argparse.ArgumentParser(description="确保 workspace/memory/YYYY-MM-DD.md 存在")
    parser.add_argument(
        "--workspace-root",
        default=os.environ.get(
            "OPENCLAW_WORKSPACE_ROOT", "/var/lib/openclaw/.openclaw/workspace"
        ),
        type=Path,
        help="OpenClaw workspace 根目录",
    )
    parser.add_argument(
        "--date",
        help="强制日期 YYYY-MM-DD（默认今日 JST）",
    )
    args = parser.parse_args()
    day = args.date or today_jst()
    mem_dir = args.workspace_root / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    path = mem_dir / f"{day}.md"
    if path.exists():
        print(f"MEMORY_OK exists {path}")
        return 0
    path.write_text(f"# {day}\n\n", encoding="utf-8")
    print(f"MEMORY_OK created {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
