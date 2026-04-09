#!/usr/bin/env python3
"""SSH 到 OpenClaw 宿主机执行诊断：服务、监听端口、本机 /line/webhook、gateway 配置片段、frpc 片段。"""
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
echo "=== systemctl openclaw ==="
systemctl is-active openclaw.service 2>&1
echo "=== ss LISTEN (node/openclaw/18789) ==="
ss -tlnp 2>/dev/null | grep -E '18789|openclaw|node' || ss -tlnp 2>/dev/null | head -40
echo "=== openclaw.json gateway top-level ==="
python3 <<'PY'
import json
from pathlib import Path
p = Path("/var/lib/openclaw/.openclaw/openclaw.json")
if p.exists():
    d = json.loads(p.read_text(encoding="utf-8"))
    g = d.get("gateway") or {}
    print(json.dumps({"gateway": g}, indent=2, ensure_ascii=False))
else:
    print("missing", p)
PY
echo "=== curl loopback /line/webhook (18789) ==="
curl -sS -o /dev/null -w "HTTP %{http_code}\n" --connect-timeout 3 "http://127.0.0.1:18789/line/webhook" 2>&1
echo "=== curl if port in env PORT_TRY ==="
P="${PORT_TRY:-18789}"
curl -sS -o /dev/null -w "HTTP %{http_code} port=$P\n" --connect-timeout 3 "http://127.0.0.1:${P}/line/webhook" 2>&1
echo "=== frpc.toml head ==="
test -f /etc/frp/frpc.toml && head -80 /etc/frp/frpc.toml || echo "no /etc/frp/frpc.toml"
echo "=== journal openclaw last 15 lines ==="
journalctl -u openclaw -n 15 --no-pager 2>&1
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
        timeout=45,
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
