#!/usr/bin/env python3
"""SSH 到汤猴宿主机，打印 /etc/frp/frpc.toml 全文（只读，不改配置）。"""
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


def main() -> int:
    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    try:
        import paramiko
    except ImportError:
        print("缺少 paramiko", file=sys.stderr)
        return 1
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=pw, timeout=60, allow_agent=False, look_for_keys=False)
    _, so, se = c.exec_command(
        "set -e; test -f /etc/frp/frpc.toml && cat /etc/frp/frpc.toml || echo 'MISSING /etc/frp/frpc.toml'",
        get_pty=True,
    )
    out = so.read().decode("utf-8", errors="replace")
    err = se.read().decode("utf-8", errors="replace")
    c.close()
    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    var_dir = _SCRIPTS.parent / "var"
    try:
        var_dir.mkdir(parents=True, exist_ok=True)
        snap = var_dir / "remote_frpc_frpc.toml.snapshot.txt"
        snap.write_text(out, encoding="utf-8")
        print(f"\n[已落盘] {snap}", file=sys.stderr)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
