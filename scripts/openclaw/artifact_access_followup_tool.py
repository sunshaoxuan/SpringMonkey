#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from artifact_registry import DEFAULT_STATE_PATH as DEFAULT_ARTIFACT_STATE_PATH
from artifact_registry import load_latest_artifact
from google_doc_delivery import authorize_document


DOC_URL_RE = re.compile(r"https://docs\.google\.com/document/d/[^\s)>\"]+")
EMAIL_RE = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}")


def resolve_recipient(text: str, configured_email: str) -> str:
    # Only the current owner request supplies overrides, never document content.
    emails = list(dict.fromkeys(match.lower() for match in EMAIL_RE.findall(text)))
    if len(emails) > 1:
        raise ValueError("消息包含多个邮箱，请明确本次需要授权的一个账号。")
    return emails[0] if emails else configured_email.strip()

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def resolve_artifact(
    text: str,
    *,
    artifact_state: Path = DEFAULT_ARTIFACT_STATE_PATH,
) -> tuple[dict[str, Any] | None, str]:
    explicit = DOC_URL_RE.search(text)
    if explicit:
        return {"job_name": "explicit artifact URL"}, explicit.group(0).rstrip(".,，。")
    artifact = load_latest_artifact(artifact_state)
    if artifact:
        return {"job_name": str(artifact.get("source") or "artifact registry")}, str(artifact["url"])
    return None, ""


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text or "")


def run_access_verification(
    doc_url: str,
    owner_email: str,
    *,
    timeout_seconds: int,
) -> tuple[bool, str]:
    try:
        receipt = authorize_document(doc_url, owner_email)
    except Exception as exc:
        return False, f"未完成：权限核验失败（{type(exc).__name__}）。请检查浏览器登录和共享设置。"
    ok = receipt.get("viewer_verified") is True and receipt.get("general_access") == "restricted"
    return ok, "已授权查看，已重新打开文档核验，常规访问为受限。" if ok else "未完成：缺少已保存的查看权限凭据。"


def build_reply(
    task: dict[str, Any] | None,
    doc_url: str,
    *,
    execute_agent: bool = False,
    agent_timeout: int = 900,
    owner_email: str = "",
    request_text: str = "",
) -> str:
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
        try:
            owner_email = resolve_recipient(request_text, owner_email)
        except ValueError as exc:
            lines[3] = f"执行结果：未完成：{exc}"
            lines[4] = "当前状态：等待明确授权账号。"
            return "\n".join(lines)
        if not owner_email.strip():
            ok, result = False, "未完成：主机未配置 OPENCLAW_OWNER_GOOGLE_EMAIL。"
        else:
            ok, result = run_access_verification(doc_url, owner_email.strip(), timeout_seconds=agent_timeout)
        lines[3] = f"执行结果：{result}"
        lines[4] = "当前状态：已证明 Google Docs 查看权限已经授予。" if ok else "当前状态：权限处理未完成。"
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify and report follow-up access work for recent delivered artifacts.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--message-timestamp", default="")
    parser.add_argument("--artifact-state", type=Path, default=DEFAULT_ARTIFACT_STATE_PATH)
    parser.add_argument("--execute-agent", action="store_true")
    parser.add_argument("--agent-timeout", type=int, default=900)
    parser.add_argument("--owner-email", default=os.environ.get("OPENCLAW_OWNER_GOOGLE_EMAIL", ""))
    args = parser.parse_args()
    task, doc_url = resolve_artifact(
        args.text,
        artifact_state=args.artifact_state,
    )
    reply = build_reply(
            task,
            doc_url,
            execute_agent=args.execute_agent,
            agent_timeout=args.agent_timeout,
            owner_email=args.owner_email,
            request_text=args.text,
        )
    print(reply)
    return 0 if not args.execute_agent or "当前状态：已证明 Google Docs 查看权限已经授予。" in reply else 1


if __name__ == "__main__":
    raise SystemExit(main())
