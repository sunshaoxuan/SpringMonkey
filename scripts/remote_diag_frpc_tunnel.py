#!/usr/bin/env python3
"""
SSH 到汤猴宿主机，打印 frpc 与 LINE webhook 隧道相关证据（不改配置）。

说明：remotePort（如 31879）在 **frps 所在机（通常为 ccnode）** 上监听；
汤猴上只会看到本机 127.0.0.1:localPort。若在 ccnode 上看不到公网端口，请对照本输出里的 frpc 日志与 frps allowPorts。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint

HOST = os.environ.get("OPENCLAW_SSH_HOST", "ccnode.briconbric.com")
PORT = int(os.environ.get("OPENCLAW_SSH_PORT", "8822"))
USER = "root"

REMOTE = r"""
set +e
echo "=== /etc/frp/frpc.toml (line_webhook / server) ==="
grep -nE "serverAddr|serverPort|auth|line_webhook|18789|31879" /etc/frp/frpc.toml 2>&1 || true
echo ""
echo "=== systemctl frpc ==="
systemctl is-active frpc.service 2>&1
systemctl status frpc.service --no-pager -n 15 2>&1
echo ""
echo "=== journal frpc (last 50) ==="
journalctl -u frpc.service -n 50 --no-pager 2>&1
echo ""
echo "=== ss 本机 18789 ==="
ss -tlnp 2>/dev/null | grep 18789 || true
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
        print("缺少 paramiko，见 requirements-ssh.txt", file=sys.stderr)
        return 1
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=pw, timeout=60, allow_agent=False, look_for_keys=False)
    _, so, se = c.exec_command(REMOTE, get_pty=True)
    print(so.read().decode("utf-8", errors="replace"))
    err = se.read().decode("utf-8", errors="replace")
    if err.strip():
        print(err, file=sys.stderr)
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
