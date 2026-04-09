#!/usr/bin/env python3
"""SSH 到汤猴宿主机，检查 LINE 通道是否已启用（只读诊断）。"""
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

REMOTE_SH = r"""
set +e
echo "=== systemctl openclaw ==="
systemctl is-active openclaw.service 2>&1
systemctl status openclaw.service --no-pager -n 20 2>&1

echo "=== channels.line in openclaw.json ==="
python3 <<'PY'
import json
from pathlib import Path
p = Path("/var/lib/openclaw/.openclaw/openclaw.json")
if not p.exists():
    print("missing", p)
    raise SystemExit(0)
d = json.loads(p.read_text(encoding="utf-8"))
line = (d.get("channels") or {}).get("line")
print(json.dumps({"channels.line": line}, ensure_ascii=False, indent=2))
PY

echo "=== line secret files ==="
for f in \
  /var/lib/openclaw/.openclaw/secrets/line-channel-access-token.txt \
  /var/lib/openclaw/.openclaw/secrets/line-channel-secret.txt
do
  if [ -f "$f" ]; then
    sz="$(wc -c < "$f" 2>/dev/null || echo 0)"
    echo "OK $f bytes=$sz"
  else
    echo "MISSING $f"
  fi
done

echo "=== local webhook probe ==="
curl -sS -o /dev/null -w "HTTP %{http_code}\n" --connect-timeout 5 "http://127.0.0.1:18789/line/webhook" 2>&1

echo "=== openclaw journal last 40 ==="
journalctl -u openclaw.service -n 40 --no-pager 2>&1
"""


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
    _, so, se = c.exec_command(REMOTE_SH.strip(), get_pty=True)
    out = so.read().decode("utf-8", errors="replace")
    err = se.read().decode("utf-8", errors="replace")
    c.close()
    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
