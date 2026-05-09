#!/usr/bin/env python3
"""Install a systemd timer that polls and closes SpringMonkey long tasks."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = os.environ.get("OPENCLAW_SSH_HOST", "ccnode.briconbric.com")
PORT = int(os.environ.get("OPENCLAW_SSH_PORT", "8822"))
USER = os.environ.get("OPENCLAW_SSH_USER", "root")
REPO = os.environ.get("SPRINGMONKEY_REPO_PATH", "/var/lib/openclaw/repos/SpringMonkey")

REMOTE = r"""
set -euo pipefail
cd "$SPRINGMONKEY_REPO_PATH"

cat >/etc/systemd/system/openclaw-long-task-supervisor.service <<EOF
[Unit]
Description=SpringMonkey OpenClaw long task supervisor
After=network-online.target openclaw.service
Wants=network-online.target

[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory=$SPRINGMONKEY_REPO_PATH
Environment=HOME=/var/lib/openclaw
EnvironmentFile=-/etc/openclaw/openclaw.env
ExecStart=/usr/bin/python3 $SPRINGMONKEY_REPO_PATH/scripts/openclaw/long_task_supervisor.py poll --deliver
EOF

cat >/etc/systemd/system/openclaw-long-task-supervisor.timer <<'EOF'
[Unit]
Description=Poll SpringMonkey OpenClaw long task supervisor every minute

[Timer]
OnBootSec=90s
OnUnitActiveSec=60s
AccuracySec=10s
Unit=openclaw-long-task-supervisor.service
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now openclaw-long-task-supervisor.timer
systemctl list-timers openclaw-long-task-supervisor.timer --no-pager
systemctl start openclaw-long-task-supervisor.service || true
systemctl status openclaw-long-task-supervisor.service --no-pager -n 40 || true
echo LONG_TASK_SUPERVISOR_TIMER_OK
"""


def main() -> int:
    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    try:
        import paramiko
    except ImportError:
        print("paramiko is required for remote install", file=sys.stderr)
        return 1
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=60, look_for_keys=False, allow_agent=False)
    env = f"export SPRINGMONKEY_REPO_PATH={REPO!r}\n"
    _, stdout, stderr = client.exec_command(env + REMOTE, get_pty=True, timeout=600)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    return 0 if "LONG_TASK_SUPERVISOR_TIMER_OK" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
