#!/usr/bin/env python3
"""
在网关宿主机上执行：pull → ensure_daily_memory → apply → verify ×2 → restart openclaw。
需可读 HOST_ACCESS.md（密码）或环境变量 SPRINGMONKEY_SSH_PASSWORD。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

try:
    import paramiko
except ImportError:
    paramiko = None  # type: ignore


def find_password() -> str:
    envp = os.environ.get("SPRINGMONKEY_SSH_PASSWORD", "").strip()
    if envp:
        return envp
    here = Path(__file__).resolve().parent
    for _ in range(8):
        cand = here / "HOST_ACCESS.md"
        if cand.is_file():
            m = re.search(r"- Password:\s*`([^`]+)`", cand.read_text(encoding="utf-8"))
            if m:
                return m.group(1)
        if here.parent == here:
            break
        here = here.parent
    # 工作区根 default/HOST_ACCESS.md
    alt = Path(r"c:\tmp\default\HOST_ACCESS.md")
    if alt.is_file():
        m = re.search(r"- Password:\s*`([^`]+)`", alt.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return ""


def main() -> int:
    if paramiko is None:
        print("pip install paramiko", file=sys.stderr)
        return 2
    pw = find_password()
    if not pw:
        print("no SSH password", file=sys.stderr)
        return 2
    cmd = r"""set -e
cd /var/lib/openclaw/repos/SpringMonkey
git fetch origin
git checkout -- . 2>/dev/null || true
git clean -fd scripts/news/jobs/ 2>/dev/null || true
git pull --ff-only origin main || git pull --ff-only
python3 scripts/news/ensure_daily_memory.py
python3 scripts/news/apply_news_config.py
python3 scripts/news/verify_news_config.py
python3 scripts/news/verify_runtime_readiness.py
systemctl restart openclaw.service
sleep 12
systemctl is-active openclaw.service
echo DEPLOY_HOST_OK
"""
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    host = os.environ.get("SPRINGMONKEY_SSH_HOST", "ccnode.briconbric.com")
    port = int(os.environ.get("SPRINGMONKEY_SSH_PORT", "8822"))
    user = os.environ.get("SPRINGMONKEY_SSH_USER", "root")
    c.connect(hostname=host, port=port, username=user, password=pw, timeout=90)
    _, out, err = c.exec_command(cmd, timeout=600)
    sys.stdout.write(out.read().decode("utf-8", errors="replace"))
    sys.stderr.write(err.read().decode("utf-8", errors="replace"))
    code = out.channel.recv_exit_status()
    c.close()
    return code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
