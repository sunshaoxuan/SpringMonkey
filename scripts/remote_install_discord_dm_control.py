#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint


HOST = os.environ.get("OPENCLAW_SSH_HOST", "ccnode.briconbric.com")
PORT = int(os.environ.get("OPENCLAW_SSH_PORT", "8822"))
USER = os.environ.get("OPENCLAW_SSH_USER", "root")

REMOTE = r"""
set -euo pipefail

REPO="/var/lib/openclaw/repos/SpringMonkey"
WORKSPACE="/var/lib/openclaw/.openclaw/workspace"
SERVICE="/etc/systemd/system/openclaw-discord-dm-control.service"
TIMER="/etc/systemd/system/openclaw-discord-dm-control.timer"

cd "$REPO"
git remote set-url origin https://github.com/sunshaoxuan/SpringMonkey.git
git pull --ff-only

install -d -m 755 "$WORKSPACE/scripts"
install -d -m 700 "$WORKSPACE/.secure"
install -m 755 "$REPO/scripts/discord/discord_dm_control_poll.py" "$WORKSPACE/scripts/discord_dm_control_poll.py"

cat >"$SERVICE" <<'EOF'
[Unit]
Description=OpenClaw Discord owner DM control poller
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=openclaw
Group=openclaw
Environment=OPENCLAW_HOME=/var/lib/openclaw/.openclaw
ExecStart=/usr/bin/python3 /var/lib/openclaw/.openclaw/workspace/scripts/discord_dm_control_poll.py --once --max-messages 20
EOF

cat >"$TIMER" <<'EOF'
[Unit]
Description=Poll OpenClaw owner Discord DM control channel

[Timer]
OnBootSec=30s
OnUnitActiveSec=20s
AccuracySec=5s
Unit=openclaw-discord-dm-control.service

[Install]
WantedBy=timers.target
EOF

chown openclaw:openclaw "$WORKSPACE/scripts/discord_dm_control_poll.py"
systemctl daemon-reload

if [ ! -f /var/lib/openclaw/.openclaw/workspace/.secure/discord_dm_control_state.json ]; then
  runuser -u openclaw -- /usr/bin/python3 "$WORKSPACE/scripts/discord_dm_control_poll.py" --init-cursor
fi

systemctl enable --now openclaw-discord-dm-control.timer
systemctl start openclaw-discord-dm-control.service
systemctl --no-pager --full status openclaw-discord-dm-control.timer | sed -n '1,12p'
systemctl --no-pager --full status openclaw-discord-dm-control.service | sed -n '1,20p'
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
        print("缺少 paramiko。请执行：python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt", file=sys.stderr)
        return 1
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=120, allow_agent=False, look_for_keys=False)
    _, stdout, stderr = client.exec_command(REMOTE.strip(), get_pty=True, timeout=300)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
