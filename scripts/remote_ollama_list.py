#!/usr/bin/env python3
"""SSH 到网关宿主机，尝试本机访问 Ollama HTTP API 或执行 ollama list。"""
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
set +e
echo "=== curl :22545 /api/tags ==="
curl -sS --connect-timeout 5 "http://127.0.0.1:22545/api/tags" 2>&1 | head -c 120000
echo ""
echo "=== curl :11434 /api/tags ==="
curl -sS --connect-timeout 5 "http://127.0.0.1:11434/api/tags" 2>&1 | head -c 120000
echo ""
echo "=== ollama list ==="
command -v ollama >/dev/null && ollama list 2>&1 || echo "ollama CLI not in PATH"
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
    c.connect(HOST, port=PORT, username=USER, password=pw, timeout=45, allow_agent=False, look_for_keys=False)
    _, stdout, stderr = c.exec_command(REMOTE, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    c.close()
    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
