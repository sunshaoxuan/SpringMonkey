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

REPO=/var/lib/openclaw/repos/SpringMonkey
SCRIPT="${REPO}/scripts/openclaw/cron_failure_self_heal.py"
GAP_SCRIPT="${REPO}/scripts/openclaw/agent_society_runtime_record_gap.py"
if [ ! -f "$SCRIPT" ]; then
  echo "missing cron self-heal script: $SCRIPT" >&2
  exit 1
fi
if [ ! -f "$GAP_SCRIPT" ]; then
  echo "missing runtime gap script: $GAP_SCRIPT" >&2
  exit 1
fi

install -d -m 755 /etc/systemd/system
install -d -m 755 /var/lib/openclaw/.openclaw/workspace/agent_society_kernel

cat >/etc/systemd/system/openclaw-cron-failure-self-heal.service <<'EOF'
[Unit]
Description=Record OpenClaw cron failures into agent society self-improvement loop
After=openclaw.service

[Service]
Type=oneshot
User=root
ExecStart=/usr/bin/python3 /var/lib/openclaw/repos/SpringMonkey/scripts/openclaw/cron_failure_self_heal.py --root /var/lib/openclaw/.openclaw/workspace/agent_society_kernel --repo-root /var/lib/openclaw/repos/SpringMonkey --jobs-file /var/lib/openclaw/.openclaw/cron/jobs.json --journal-unit openclaw.service --tail 800
EOF

cat >/etc/systemd/system/openclaw-cron-failure-self-heal.timer <<'EOF'
[Unit]
Description=Periodic OpenClaw cron failure self-heal scan

[Timer]
OnCalendar=*:0/5
Persistent=true
RandomizedDelaySec=30s

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now openclaw-cron-failure-self-heal.timer
systemctl start openclaw-cron-failure-self-heal.service || true
sleep 2
systemctl is-active openclaw-cron-failure-self-heal.timer
systemctl status openclaw-cron-failure-self-heal.service --no-pager -n 30 || true
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

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=120, allow_agent=False, look_for_keys=False)
    _, stdout, stderr = client.exec_command(REMOTE.strip(), get_pty=True, timeout=1800)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    return 0 if "active" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
