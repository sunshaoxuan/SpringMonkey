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

REMOTE = r'''
set -euo pipefail
install -d -m 755 /usr/local/lib/openclaw /var/backups/openclaw-log-archive /etc/systemd/system
install -m 755 /var/lib/openclaw/repos/SpringMonkey/scripts/openclaw/monthly_log_retention.py /usr/local/lib/openclaw/monthly_log_retention.py

cat >/usr/local/lib/openclaw/run_monthly_log_retention.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
ARCHIVE_ROOT=/var/backups/openclaw-log-archive
CURRENT_MONTH="$(date +%Y-%m)"
PREVIOUS_MONTH="$(date -d "$(date +%Y-%m-01) -1 month" +%Y-%m)"
JOURNAL_ARCHIVE="${ARCHIVE_ROOT}/journal/openclaw-${PREVIOUS_MONTH}.journal.gz"
mkdir -p "$(dirname "$JOURNAL_ARCHIVE")"
if [ ! -s "$JOURNAL_ARCHIVE" ]; then
  START="${PREVIOUS_MONTH}-01 00:00:00"
  END="${CURRENT_MONTH}-01 00:00:00"
  journalctl -u openclaw.service --since "$START" --until "$END" --no-pager | gzip -9 > "${JOURNAL_ARCHIVE}.tmp"
  gzip -t "${JOURNAL_ARCHIVE}.tmp"
  mv "${JOURNAL_ARCHIVE}.tmp" "$JOURNAL_ARCHIVE"
fi
journalctl --vacuum-time=35d >/dev/null
python3 /usr/local/lib/openclaw/monthly_log_retention.py --archive-root "$ARCHIVE_ROOT" --min-free-percent 10
EOF
chmod 755 /usr/local/lib/openclaw/run_monthly_log_retention.sh

cat >/etc/systemd/system/openclaw-log-retention.service <<'EOF'
[Unit]
Description=Archive previous-month OpenClaw logs and protect free disk space
After=local-fs.target

[Service]
Type=oneshot
User=root
ExecStart=/usr/local/lib/openclaw/run_monthly_log_retention.sh
EOF

cat >/etc/systemd/system/openclaw-log-retention.timer <<'EOF'
[Unit]
Description=Daily OpenClaw monthly log retention check

[Timer]
OnCalendar=*-*-* 02:40:00
Persistent=true
RandomizedDelaySec=15m

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now openclaw-log-retention.timer
systemctl start openclaw-log-retention.service
systemctl is-active openclaw-log-retention.timer
systemctl status openclaw-log-retention.service --no-pager -n 30
systemctl list-timers openclaw-log-retention.timer --no-pager
df -h /
'''


def main() -> int:
    password = load_openclaw_ssh_password()
    if not password:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=password, timeout=30, allow_agent=False, look_for_keys=False)
    try:
        _, stdout, stderr = client.exec_command(REMOTE, get_pty=True, timeout=300)
        output = stdout.read().decode("utf-8", errors="replace")
        error = stderr.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
    finally:
        client.close()
    print(output)
    if error.strip():
        print(error, file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
