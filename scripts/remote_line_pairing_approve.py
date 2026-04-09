#!/usr/bin/env python3
"""SSH 到汤猴宿主机，执行 openclaw pairing approve line <CODE>（批准 LINE 配对）。"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint

HOST = os.environ.get("OPENCLAW_SSH_HOST", "ccnode.briconbric.com")
PORT = int(os.environ.get("OPENCLAW_SSH_PORT", "8822"))
USER = "root"

_CODE_RE = re.compile(r"^[A-Za-z0-9]{6,16}$")


def _code_from_args() -> str | None:
    for a in sys.argv[1:]:
        if a.strip() and not a.startswith("-"):
            return a.strip()
    return (os.environ.get("LINE_PAIRING_CODE") or os.environ.get("OPENCLAW_PAIRING_CODE") or "").strip() or None


def main() -> int:
    code = _code_from_args()
    if not code:
        print(
            "用法: python remote_line_pairing_approve.py <PAIRING_CODE>\n"
            "或: LINE_PAIRING_CODE=xxxx python remote_line_pairing_approve.py",
            file=sys.stderr,
        )
        return 2
    if not _CODE_RE.match(code):
        print("配对码格式异常，请检查。", file=sys.stderr)
        return 2

    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    try:
        import paramiko
    except ImportError:
        print("缺少 paramiko", file=sys.stderr)
        return 1

    # 仅传字母数字，避免注入
    safe = code
    remote = f"""set -e
sudo -u openclaw env HOME=/var/lib/openclaw bash -lc 'cd && openclaw pairing approve line {safe}'
echo DONE
"""

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=pw, timeout=60, allow_agent=False, look_for_keys=False)
    _, so, se = c.exec_command(remote.strip(), get_pty=True)
    out = so.read().decode("utf-8", errors="replace")
    err = se.read().decode("utf-8", errors="replace")
    c.close()
    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
