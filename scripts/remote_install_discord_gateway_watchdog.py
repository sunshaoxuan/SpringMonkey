#!/usr/bin/env python3
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
USER = os.environ.get("OPENCLAW_SSH_USER", "root")

REMOTE = r"""
set -euo pipefail

install -d -m 755 /usr/local/lib/openclaw
install -d -m 755 /var/lib/openclaw/.openclaw/state

cat >/usr/local/lib/openclaw/discord_gateway_watchdog.py <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import time
import urllib.request
from pathlib import Path

STATE = Path("/var/lib/openclaw/.openclaw/state/discord_gateway_watchdog.json")
COOLDOWN_SECONDS = 300
SINCE = "10 minutes ago"
PATTERN = "Gateway heartbeat ACK timeout"


def sh(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(data: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE)


def health_ok() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:18789/healthz", timeout=5) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
        return '"ok":true' in payload
    except Exception:
        return False


def latest_timeout_line() -> str:
    proc = sh(["journalctl", "-u", "openclaw.service", "--since", SINCE, "--no-pager", "-o", "short-iso"])
    lines = [line for line in proc.stdout.splitlines() if PATTERN in line]
    return lines[-1] if lines else ""


def main() -> int:
    state = load_state()
    line = latest_timeout_line()
    now = int(time.time())
    if not line:
        print(json.dumps({"ok": True, "action": "none", "reason": "no_recent_discord_gateway_timeout"}))
        return 0

    line_id = hashlib.sha256(line.encode("utf-8")).hexdigest()
    last_line_id = state.get("last_line_id")
    last_restart = int(state.get("last_restart_epoch") or 0)
    if line_id == last_line_id:
        print(json.dumps({"ok": True, "action": "none", "reason": "already_handled", "line": line[-300:]}))
        return 0
    if now - last_restart < COOLDOWN_SECONDS:
        print(json.dumps({"ok": True, "action": "none", "reason": "cooldown", "line": line[-300:]}))
        return 0

    before_health = health_ok()
    restart = sh(["systemctl", "restart", "openclaw.service"])
    time.sleep(35)
    active = sh(["systemctl", "is-active", "openclaw.service"]).stdout.strip()
    after_health = health_ok()
    state.update(
        {
            "last_line_id": line_id,
            "last_restart_epoch": now,
            "last_timeout_line": line,
            "last_restart_returncode": restart.returncode,
            "last_active": active,
            "last_health_before": before_health,
            "last_health_after": after_health,
        }
    )
    save_state(state)
    print(json.dumps({"ok": after_health and active == "active", "action": "restart_openclaw", "active": active, "healthBefore": before_health, "healthAfter": after_health, "line": line[-300:]}, ensure_ascii=False))
    return 0 if active == "active" and after_health else 1


if __name__ == "__main__":
    raise SystemExit(main())
PY

chmod 755 /usr/local/lib/openclaw/discord_gateway_watchdog.py

cat >/etc/systemd/system/openclaw-discord-gateway-watchdog.service <<'EOF'
[Unit]
Description=OpenClaw Discord Gateway Watchdog
After=network-online.target openclaw.service

[Service]
Type=oneshot
User=root
ExecStart=/usr/bin/python3 /usr/local/lib/openclaw/discord_gateway_watchdog.py
EOF

cat >/etc/systemd/system/openclaw-discord-gateway-watchdog.timer <<'EOF'
[Unit]
Description=Run OpenClaw Discord Gateway Watchdog every minute

[Timer]
OnBootSec=2min
OnUnitActiveSec=60s
Unit=openclaw-discord-gateway-watchdog.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now openclaw-discord-gateway-watchdog.timer
systemctl start openclaw-discord-gateway-watchdog.service
systemctl is-active openclaw-discord-gateway-watchdog.timer
journalctl -u openclaw-discord-gateway-watchdog.service -n 30 --no-pager
echo DONE
"""


def main() -> int:
    password = load_openclaw_ssh_password()
    if not password:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    try:
        import paramiko
    except ImportError:
        print("paramiko is required. Run: python -m pip install -r scripts/requirements-ssh.txt", file=sys.stderr)
        return 1

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=password, timeout=120, allow_agent=False, look_for_keys=False)
    try:
        _, stdout, stderr = client.exec_command(REMOTE, get_pty=True, timeout=240)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
    finally:
        client.close()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    return 0 if "DONE" in out and "active" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
