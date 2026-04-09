#!/usr/bin/env python3
"""SSH 经 ccnode:8822 到汤猴：将 LINE 设为 dmPolicy=open、重启 openclaw；结果写入 var/last_remote_line_connect.txt"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))
from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint

OUT = _ROOT.parent / "var" / "last_remote_line_connect.txt"

REMOTE = r"""
set -e
python3 <<'PY'
import json
from pathlib import Path
p = Path("/var/lib/openclaw/.openclaw/openclaw.json")
if not p.is_file():
    raise SystemExit("missing openclaw.json")
d = json.loads(p.read_text(encoding="utf-8"))
d.setdefault("channels", {})
line = d.get("channels", {}).get("line") or {}
line["enabled"] = True
line["dmPolicy"] = "open"
line.setdefault("tokenFile", "/var/lib/openclaw/.openclaw/secrets/line-channel-access-token.txt")
line.setdefault("secretFile", "/var/lib/openclaw/.openclaw/secrets/line-channel-secret.txt")
d["channels"]["line"] = line
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("OK channels.line.dmPolicy=", line.get("dmPolicy"))
PY
systemctl restart openclaw.service
sleep 8
echo "openclaw:" $(systemctl is-active openclaw.service)
curl -sS -o /dev/null -w "webhook_http=%{http_code}\n" --connect-timeout 8 "http://127.0.0.1:18789/line/webhook" 2>&1 || true
ss -tlnp 2>/dev/null | grep -E '18789|openclaw|node' || true
echo DONE
"""


def main() -> int:
    lines: list[str] = []
    pw = load_openclaw_ssh_password()
    if not pw:
        lines.append(missing_password_hint())
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(lines), encoding="utf-8")
        return 1
    try:
        import paramiko
    except ImportError as e:
        lines.append(f"缺少 paramiko: {e}")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(lines), encoding="utf-8")
        return 1

    import os

    host = os.environ.get("OPENCLAW_SSH_HOST", "ccnode.briconbric.com")
    port = int(os.environ.get("OPENCLAW_SSH_PORT", "8822"))

    lines.append(f"connect {host}:{port} as root ...")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        c.connect(host, port=port, username="root", password=pw, timeout=90, allow_agent=False, look_for_keys=False)
    except Exception as e:
        lines.append(f"SSH connect failed: {e!r}")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(lines), encoding="utf-8")
        return 1

    _, so, se = c.exec_command(REMOTE.strip(), get_pty=True)
    out = so.read().decode("utf-8", errors="replace")
    err = se.read().decode("utf-8", errors="replace")
    c.close()
    lines.append("--- stdout ---")
    lines.append(out)
    if err.strip():
        lines.append("--- stderr ---")
        lines.append(err)
    ok = "DONE" in out
    lines.append(f"--- success={ok} ---")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
