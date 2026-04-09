#!/usr/bin/env python3
"""
远程执行 OpenClaw 配置修复（doctor --fix）并重启服务。

适用场景：
- 日志出现 Config invalid / legacy key 提示（例如 discord allow -> enabled）。
- 服务反复重启，但 root cause 指向配置 schema，而非运行权限问题。

环境变量：
- OPENCLAW_SSH_PASSWORD 或 SSH_ROOT_PASSWORD

依赖：
- paramiko（一次安装，见 docs/ops/SSH_TOOLCHAIN.md）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint

HOST = "ccnode.briconbric.com"
PORT = 8822
USER = "root"

REMOTE = r"""
set -e
echo "=== before status ==="
systemctl is-active openclaw.service || true
journalctl -u openclaw -n 40 --no-pager || true

echo "=== run doctor --fix as openclaw ==="
sudo -u openclaw -H env HOME=/var/lib/openclaw openclaw doctor --fix || true

echo "=== restart openclaw ==="
systemctl restart openclaw.service
sleep 3
systemctl is-active openclaw.service || true

echo "=== after logs ==="
journalctl -u openclaw -n 60 --no-pager || true
echo "DONE"
"""


def main() -> int:
    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1

    try:
        import paramiko
    except ImportError:
        print(
            "缺少 paramiko。请执行一次：\n"
            "  python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt\n"
            "说明：SpringMonkey/docs/ops/SSH_TOOLCHAIN.md",
            file=sys.stderr,
        )
        return 1

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST,
        port=PORT,
        username=USER,
        password=pw,
        timeout=90,
        allow_agent=False,
        look_for_keys=False,
    )
    stdin, stdout, stderr = client.exec_command(REMOTE, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
