#!/usr/bin/env python3
"""
从磁盘上的 HOST_ACCESS.md 读取 SSH 密码并运行 integration_verify_host。

查找顺序：
  1) 环境变量 SPRINGMONKEY_HOST_ACCESS_FILE
  2) 自本文件向上最多 6 层目录中的 HOST_ACCESS.md

勿将密码写入仓库；HOST_ACCESS 通常在工作区根目录（与 SpringMonkey 并列）。
"""
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "integration_verify_host.py"


def find_access() -> Path | None:
    envp = os.environ.get("SPRINGMONKEY_HOST_ACCESS_FILE", "").strip()
    if envp:
        p = Path(envp)
        return p if p.is_file() else None
    here = Path(__file__).resolve().parent
    for _ in range(8):
        cand = here / "HOST_ACCESS.md"
        if cand.is_file():
            return cand
        if here.parent == here:
            break
        here = here.parent
    return None


def main() -> int:
    access = find_access()
    if not access:
        print("Set SPRINGMONKEY_HOST_ACCESS_FILE or place HOST_ACCESS.md above this repo.", file=sys.stderr)
        return 2
    text = access.read_text(encoding="utf-8")
    m = re.search(r"- Password:\s*`([^`]+)`", text)
    if not m:
        print("no password in", access, file=sys.stderr)
        return 2
    env = os.environ.copy()
    env["SPRINGMONKEY_SSH_PASSWORD"] = m.group(1)
    extra = sys.argv[1:]
    if not extra:
        # 默认：拉代码契约 + 不强制 pull（避免无网络时失败）；需要部署补丁时显式传 --apply-v6 等
        extra = ["--full-contract", "--no-pull"]
    cmd = [sys.executable, str(SCRIPT)] + extra
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
