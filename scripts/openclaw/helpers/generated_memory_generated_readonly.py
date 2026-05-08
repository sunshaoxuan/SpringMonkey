#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


TOOL_ID = "memory.generated_readonly"
DOMAIN = "memory"
REFERENCE_TOOL_ID = "memory.curator.xhs"

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def run_command(args: list[str], timeout: int = 20) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=repo_root(),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return proc.returncode == 0, (proc.stdout or "").strip()
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def memory_query(text: str) -> str:
    query = text or "小红书 Costco Frutteto 投稿"
    ok, output = run_command(["openclaw", "ltm", "search", query, "--limit", "5"], timeout=40)
    if ok and output:
        return output
    return "长记忆查询未返回结果；请检查 memory-lancedb 或 embedding/text fallback。"


def self_status() -> str:
    ok, output = run_command([sys.executable, "scripts/openclaw/self_evolution_status.py", "--limit", "5"])
    return output if ok and output else "自演进状态暂不可用。"


def config_check() -> str:
    registry = repo_root() / "config" / "openclaw" / "intent_tools.json"
    if not registry.is_file():
        return "未找到 intent tool registry。"
    data = json.loads(registry.read_text(encoding="utf-8"))
    tools = data.get("tools", [])
    return f"注册工具数量：{len(tools)}；参考工具：{REFERENCE_TOOL_ID}。"


def answer(text: str) -> str:
    combined = f"{text} {DOMAIN}"
    if DOMAIN == "memory" or re.search(r"长记忆|記憶|memory|小红书|xhs", combined, re.I):
        return memory_query(text)
    if DOMAIN == "self" or re.search(r"自演进|自進化|能力缺口|修复包|修復包|状态|狀態", combined, re.I):
        return self_status()
    if re.search(r"配置|注册|registry|工具", combined, re.I):
        return config_check()
    return f"只读语义 helper 已处理请求：{text or '未提供文本'}"


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Semantic read-only helper generated for {TOOL_ID}.")
    parser.add_argument("--text", default="")
    parser.add_argument("--message-timestamp", default="")
    parser.add_argument("--topic", default="")
    parser.add_argument("--since", default="")
    parser.add_argument("--write", default="false")
    parser.add_argument("--forget-marked", default="false")
    parser.add_argument("--limit", default="")
    args, _unknown = parser.parse_known_args()
    result = answer(args.text)
    print(json.dumps({
        "status": "success",
        "tool_id": TOOL_ID,
        "domain": DOMAIN,
        "reference_tool_id": REFERENCE_TOOL_ID,
        "result": result,
        "trace": {
            "semantic_helper": True,
            "message_timestamp": args.message_timestamp,
        },
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
