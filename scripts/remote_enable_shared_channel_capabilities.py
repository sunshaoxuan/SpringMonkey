#!/usr/bin/env python3
"""SSH 到汤猴宿主机，统一 Discord / LINE 的共享能力入口。"""
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
set -e
install -d -m 755 /etc/openclaw
install -d -m 755 /etc/systemd/system/openclaw.service.d

if [ ! -f /etc/openclaw/openclaw.env ]; then
  install -m 640 -o root -g openclaw /dev/null /etc/openclaw/openclaw.env
fi

cat >/etc/systemd/system/openclaw.service.d/10-shared-capabilities.conf <<'EOF'
[Service]
EnvironmentFile=-/etc/openclaw/openclaw.env
EOF

python3 <<'PY'
import json
import shutil
from datetime import datetime
from pathlib import Path

p = Path("/var/lib/openclaw/.openclaw/openclaw.json")
ts = datetime.now().strftime("%Y%m%d-%H%M%S")
bak = p.with_name(f"openclaw.json.bak-shared-capabilities-{ts}")
shutil.copy2(p, bak)

d = json.loads(p.read_text(encoding="utf-8"))
tools = d.setdefault("tools", {})
web = tools.setdefault("web", {})
search = web.setdefault("search", {})
search["enabled"] = True
search.setdefault("provider", "brave")

elevated = tools.setdefault("elevated", {})
elevated["enabled"] = True
allow_from = elevated.setdefault("allowFrom", {})
for channel in ("discord", "line"):
    current = allow_from.get(channel)
    if current == ["*"]:
        continue
    items = []
    if isinstance(current, list):
        items = [str(x) for x in current]
    if "*" not in items:
        items.append("*")
    allow_from[channel] = items or ["*"]

p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(
    {
        "backup": str(bak),
        "allowFrom": elevated.get("allowFrom"),
        "search": search,
    },
    ensure_ascii=False,
    indent=2,
))
PY

systemctl daemon-reload
systemctl restart openclaw.service
sleep 8
systemctl is-active openclaw.service

python3 <<'PY'
import json
import subprocess
from pathlib import Path

p = Path("/var/lib/openclaw/.openclaw/openclaw.json")
d = json.loads(p.read_text(encoding="utf-8"))
pid = subprocess.check_output("pgrep -f 'openclaw-gateway$' | tail -1", shell=True, text=True).strip()
env_items = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
present = {}
for item in env_items:
    if item.startswith(b"BRAVE_API_KEY="):
        _, value = item.decode("utf-8", errors="replace").split("=", 1)
        present["BRAVE_API_KEY"] = (value[:6] + "..." + value[-4:]) if value else ""
print(json.dumps(
    {
        "pid": pid,
        "allowFrom": (((d.get("tools") or {}).get("elevated") or {}).get("allowFrom")),
        "braveEnv": present,
    },
    ensure_ascii=False,
    indent=2,
))
PY

curl -sS -o /dev/null -w "line_webhook_http=%{http_code}\n" --connect-timeout 5 "http://127.0.0.1:18789/line/webhook" 2>&1 || true
echo DONE
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
            "  python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt",
            file=sys.stderr,
        )
        return 1

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=pw, timeout=60, allow_agent=False, look_for_keys=False)
    _, so, se = c.exec_command(REMOTE.strip(), get_pty=True)
    out = so.read().decode("utf-8", errors="replace")
    err = se.read().decode("utf-8", errors="replace")
    c.close()
    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
