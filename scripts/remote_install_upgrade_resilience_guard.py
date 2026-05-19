#!/usr/bin/env python3
"""Install a host guard that reapplies and verifies SpringMonkey runtime layers after OpenClaw upgrades."""
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
REPO = os.environ.get("SPRINGMONKEY_REPO_PATH", "/var/lib/openclaw/repos/SpringMonkey")

REMOTE = r"""
set -euo pipefail
export HOME=/var/lib/openclaw
cd "$SPRINGMONKEY_REPO_PATH"

install -d -m 755 /usr/local/lib/openclaw
install -d -m 755 /etc/systemd/system/openclaw.service.d

cat >/usr/local/lib/openclaw/ensure_springmonkey_upgrade_resilience.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
export HOME=/var/lib/openclaw
REPO=/var/lib/openclaw/repos/SpringMonkey

if [ ! -d "$REPO" ]; then
  echo "[springmonkey-upgrade-guard] missing repo: $REPO" >&2
  exit 1
fi

cd "$REPO"

if [ -x /usr/local/lib/openclaw/ensure_memory_lancedb_guard.sh ]; then
  /usr/local/lib/openclaw/ensure_memory_lancedb_guard.sh
fi

if [ -x /usr/local/lib/openclaw/ensure_agent_society_runtime_guard.sh ]; then
  /usr/local/lib/openclaw/ensure_agent_society_runtime_guard.sh
fi

python3 scripts/openclaw/runtime_patch_inventory.py --fail-on-missing

install -d -o openclaw -g openclaw -m 775 /var/lib/openclaw/.openclaw/workspace/media/weather
install -d -o openclaw -g openclaw -m 775 /var/lib/openclaw/.openclaw/workspace/state/long_task_supervisor
install -d -o openclaw -g openclaw -m 770 /var/lib/openclaw/.openclaw/delivery-queue
chown -R openclaw:openclaw /var/lib/openclaw/.openclaw/workspace/media /var/lib/openclaw/.openclaw/workspace/state/long_task_supervisor /var/lib/openclaw/.openclaw/delivery-queue

echo "[springmonkey-upgrade-guard] ok"
EOF
chmod 755 /usr/local/lib/openclaw/ensure_springmonkey_upgrade_resilience.sh

cat >/etc/systemd/system/openclaw.service.d/40-springmonkey-upgrade-resilience.conf <<'EOF'
[Service]
ExecStartPre=/usr/local/lib/openclaw/ensure_springmonkey_upgrade_resilience.sh
EOF

systemctl daemon-reload
/usr/local/lib/openclaw/ensure_springmonkey_upgrade_resilience.sh
systemctl restart openclaw.service
sleep 8
systemctl is-active openclaw.service
python3 scripts/openclaw/runtime_patch_inventory.py --fail-on-missing
echo "UPGRADE_RESILIENCE_GUARD_INSTALLED"
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
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=90, allow_agent=False, look_for_keys=False)
    env = f"export SPRINGMONKEY_REPO_PATH={REPO!r}\n"
    _, stdout, stderr = client.exec_command(env + REMOTE, get_pty=True, timeout=900)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    return 0 if "UPGRADE_RESILIENCE_GUARD_INSTALLED" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
