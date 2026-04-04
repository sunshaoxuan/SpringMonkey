#!/usr/bin/env python3
"""从仓库旁 HOST_ACCESS.md 取密码并运行 integration_verify_host（仅本地运维使用，勿提交密码）。"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ACCESS = ROOT / "HOST_ACCESS.md"
SCRIPT = Path(__file__).resolve().parent / "integration_verify_host.py"


def main() -> int:
    if not ACCESS.exists():
        print("missing", ACCESS, file=sys.stderr)
        return 2
    text = ACCESS.read_text(encoding="utf-8")
    m = re.search(r"- Password:\s*`([^`]+)`", text)
    if not m:
        print("no password in HOST_ACCESS", file=sys.stderr)
        return 2
    env = os.environ.copy()
    env["SPRINGMONKEY_SSH_PASSWORD"] = m.group(1)
    extra = sys.argv[1:]
    cmd = [sys.executable, str(SCRIPT)] + extra
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
