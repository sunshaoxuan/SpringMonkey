#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


DEFAULT_STATE_PATH = Path("/var/lib/openclaw/.openclaw/workspace/state/long_task_supervisor/tasks.json")
DOC_URL_RE = re.compile(r"https://docs\.google\.com/document/d/[^\s)>\"]+")

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def load_tasks(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    tasks = data.get("tasks") if isinstance(data, dict) else []
    return [task for task in tasks if isinstance(task, dict)]


def latest_artifact(tasks: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    for task in reversed(tasks):
        text = str(task.get("final_report") or "")
        match = DOC_URL_RE.search(text)
        if match:
            return task, match.group(0).rstrip(".,，。")
    return None, ""


def build_reply(task: dict[str, Any] | None, doc_url: str) -> str:
    lines = [
        "交付物访问请求已识别。",
        "结论：这不是文件生成状态查询，不能只回复“任务成功”。",
    ]
    if not task or not doc_url:
        lines.extend(
            [
                "状态：未找到最近交付物链接。",
                "下一步：先定位最近一次已交付文件，再处理查看权限或共享权限。",
            ]
        )
        return "\n".join(lines)
    title = str(task.get("job_name") or task.get("job_id") or "recent delivered artifact")
    lines.extend(
        [
            f"目标文件：{doc_url}",
            f"来源任务：{title}",
            "当前状态：已定位交付物；尚未证明 Google Docs 查看权限已经授予。",
            "下一步：打开该文档的共享设置，授予当前 owner 可查看权限；完成后必须报告“已授权查看”，如果无法修改权限则报告具体阻断点。",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify and report follow-up access work for recent delivered artifacts.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--message-timestamp", default="")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    args = parser.parse_args()
    task, doc_url = latest_artifact(load_tasks(args.state))
    print(build_reply(task, doc_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
