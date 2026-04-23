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
USER = "root"

REMOTE = r"""
set -euo pipefail

REPO=/var/lib/openclaw/repos/SpringMonkey
BIN=/usr/local/lib/openclaw
SCRIPT=$BIN/repo_sync_springmonkey.sh

install -d -m 755 "$BIN"

cat >"$SCRIPT" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

REPO=/var/lib/openclaw/repos/SpringMonkey
LOGDIR=/var/log/openclaw
LOG=$LOGDIR/repo-sync.log

mkdir -p "$LOGDIR"
touch "$LOG"

{
  echo "=== repo-sync $(date -Is) ==="
  if [ ! -d "$REPO/.git" ]; then
    echo "missing repo: $REPO"
    exit 1
  fi
  cd "$REPO"
  git fetch origin --prune
  git merge --no-edit origin/main
  git status -sb
} >>"$LOG" 2>&1
EOF

chmod 755 "$SCRIPT"

cat >/etc/systemd/system/openclaw-repo-sync.service <<'EOF'
[Unit]
Description=Sync SpringMonkey repo on OpenClaw host
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/lib/openclaw/repo_sync_springmonkey.sh
User=root
EOF

cat >/etc/systemd/system/openclaw-repo-sync.timer <<'EOF'
[Unit]
Description=Periodic SpringMonkey repo sync

[Timer]
OnBootSec=8min
OnUnitActiveSec=10min
Persistent=true
Unit=openclaw-repo-sync.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now openclaw-repo-sync.timer
systemctl start openclaw-repo-sync.service
systemctl is-active openclaw-repo-sync.timer
systemctl status openclaw-repo-sync.service --no-pager -n 20 || true
tail -n 20 /var/log/openclaw/repo-sync.log || true
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
    _, stdout, stderr = client.exec_command(REMOTE.strip(), get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    return 0 if "active" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
