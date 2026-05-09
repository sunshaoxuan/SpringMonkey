#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
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


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text or "")


def run_access_agent(doc_url: str, *, timeout_seconds: int) -> tuple[bool, str]:
    prompt = (
        "请处理最近一次已交付文档的查看权限问题。\n"
        f"目标文档：{doc_url}\n"
        "用户明确要求：给 owner 查看文件的许可。不要重复报告文件生成任务成功。"
        "请使用已登录的 Google Docs/Drive 浏览器会话打开共享设置，授予当前 owner 可查看权限；"
        "如果无法修改权限，只报告具体阻断点。完成后用中文说明“已授权查看”或“未完成：原因”。"
    )
    try:
        proc = subprocess.run(
            [
                "openclaw",
                "--no-color",
                "agent",
                "--agent",
                "main",
                "--message",
                prompt,
                "--timeout",
                str(timeout_seconds),
                "--thinking",
                "medium",
                "--json",
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds + 60,
        )
    except Exception as exc:
        return False, f"未完成：无法启动权限处理 agent：{type(exc).__name__}: {exc}"
    output = strip_ansi(proc.stdout or "").strip()
    if proc.returncode != 0:
        return False, f"未完成：权限处理 agent 退出码 {proc.returncode}。"
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return ("已授权查看" in output), output[-700:] or "未完成：权限处理 agent 没有返回可读结果。"
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    text = ""
    payloads = result.get("payloads") if isinstance(result.get("payloads"), list) else []
    for item in payloads:
        if isinstance(item, dict) and str(item.get("text") or "").strip():
            text = str(item.get("text") or "").strip()
            break
    text = text or str((result.get("meta") or {}).get("finalAssistantVisibleText") or "").strip()
    ok = str(payload.get("status") or "") == "ok" and "已授权查看" in text
    return ok, text or "未完成：权限处理 agent 没有返回最终结论。"


def build_reply(task: dict[str, Any] | None, doc_url: str, *, execute_agent: bool = False, agent_timeout: int = 900) -> str:
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
            "下一步：打开该文档的共享设置，授予当前 owner 可查看权限；完成后必须报告“已授权查看”，如果无法修改权限则报告具体阻断点。",
            "当前状态：已定位交付物；尚未证明 Google Docs 查看权限已经授予。",
            f"来源任务：{title}",
        ]
    )
    if execute_agent:
        ok, result = run_access_agent(doc_url, timeout_seconds=agent_timeout)
        lines[3] = f"执行结果：{result}"
        lines[4] = "当前状态：已证明 Google Docs 查看权限已经授予。" if ok else "当前状态：权限处理未完成。"
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify and report follow-up access work for recent delivered artifacts.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--message-timestamp", default="")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--execute-agent", action="store_true")
    parser.add_argument("--agent-timeout", type=int, default=900)
    args = parser.parse_args()
    task, doc_url = latest_artifact(load_tasks(args.state))
    print(build_reply(task, doc_url, execute_agent=args.execute_agent, agent_timeout=args.agent_timeout))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
