#!/usr/bin/env python3
"""SSH 到汤猴宿主机，强制开启 LINE 通道并将 dmPolicy 设为 open。"""
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
set -e
OC_HOME="/var/lib/openclaw"
CFG="$OC_HOME/.openclaw/openclaw.json"

python3 <<'PY'
import json
from pathlib import Path
p = Path("/var/lib/openclaw/.openclaw/openclaw.json")
if not p.exists():
    raise SystemExit("missing /var/lib/openclaw/.openclaw/openclaw.json")
d = json.loads(p.read_text(encoding="utf-8"))
d.setdefault("channels", {})
line = d["channels"].get("line") or {}
line["enabled"] = True
line["dmPolicy"] = "open"
line.setdefault("tokenFile", "/var/lib/openclaw/.openclaw/secrets/line-channel-access-token.txt")
line.setdefault("secretFile", "/var/lib/openclaw/.openclaw/secrets/line-channel-secret.txt")
d["channels"]["line"] = line
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("UPDATED channels.line =", line)
PY

echo "=== token files ==="
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

echo "=== restart openclaw ==="
systemctl restart openclaw.service
sleep 2
systemctl is-active openclaw.service || true
journalctl -u openclaw.service -n 30 --no-pager || true

echo "=== local webhook ==="
curl -sS -o /dev/null -w "HTTP %{http_code}\n" --connect-timeout 5 "http://127.0.0.1:18789/line/webhook" 2>&1 || true
echo "DONE"
"""


def main() -> int:
    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        try:
            snap = _SCRIPTS.parent / "var" / "remote_line_force_open.last.txt"
            snap.parent.mkdir(parents=True, exist_ok=True)
            snap.write_text(missing_password_hint() + "\n", encoding="utf-8")
        except OSError:
            pass
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
    var_dir = _SCRIPTS.parent / "var"
    combined = out + ("\n--- stderr ---\n" + err if err.strip() else "")
    try:
        var_dir.mkdir(parents=True, exist_ok=True)
        snap = var_dir / "remote_line_force_open.last.txt"
        snap.write_text(combined, encoding="utf-8")
    except OSError:
        pass
    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
