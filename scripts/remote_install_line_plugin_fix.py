#!/usr/bin/env python3
"""SSH：为 openclaw 用户安装 @openclaw/line 并重启 gateway（修复 manifest 缺失）。"""
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
echo "=== plugins before ==="
sudo -u openclaw -H bash -lc 'export HOME=/var/lib/openclaw && cd "$HOME" && (openclaw plugins list 2>&1 || true)'

echo "=== install @openclaw/line ==="
sudo -u openclaw -H bash -lc 'export HOME=/var/lib/openclaw && cd "$HOME" && openclaw plugins install @openclaw/line' || \
sudo -u openclaw -H bash -lc 'export HOME=/var/lib/openclaw && cd "$HOME" && npx --yes @openclaw/cli plugins install @openclaw/line'

echo "=== plugins after ==="
sudo -u openclaw -H bash -lc 'export HOME=/var/lib/openclaw && cd "$HOME" && openclaw plugins list 2>&1'

echo "=== restart ==="
systemctl restart openclaw.service
sleep 4
systemctl is-active openclaw.service

echo "=== journal line (last 25) ==="
journalctl -u openclaw -n 25 --no-pager | grep -E 'line|LINE|error|Error' || journalctl -u openclaw -n 15 --no-pager

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

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        HOST,
        port=PORT,
        username=USER,
        password=pw,
        timeout=120,
        allow_agent=False,
        look_for_keys=False,
    )
    stdin, stdout, stderr = c.exec_command(REMOTE, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    c.close()
    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
