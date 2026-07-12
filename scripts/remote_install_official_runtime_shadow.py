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
REPO = os.environ.get("SPRINGMONKEY_REPO_PATH", "/var/lib/openclaw/repos/SpringMonkey")

REMOTE = r'''
set -euo pipefail
cd "$SPRINGMONKEY_REPO_PATH"

JOBS=/var/lib/openclaw/.openclaw/cron/jobs.json
STATE=/var/lib/openclaw/.openclaw/workspace/agent_society_kernel/official_runtime_shadow.json
BEFORE=$(sha256sum "$JOBS" | awk '{print $1}')

test -f scripts/openclaw/official_runtime_shadow_bridge.py
test -f config/openclaw/official_runtime_migration.json

cat >/etc/systemd/system/openclaw-official-runtime-shadow.service <<EOF
[Unit]
Description=Shadow OpenClaw official Tasks Doctor and Health for SpringMonkey governance
After=openclaw.service

[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory=$SPRINGMONKEY_REPO_PATH
Environment=HOME=/var/lib/openclaw
EnvironmentFile=-/etc/openclaw/openclaw.env
ExecStart=/usr/bin/python3 $SPRINGMONKEY_REPO_PATH/scripts/openclaw/official_runtime_shadow_bridge.py --jobs-file $JOBS --state-file $STATE --enforce-cron-integrity
EOF

cat >/etc/systemd/system/openclaw-official-runtime-shadow.timer <<'EOF'
[Unit]
Description=Capture OpenClaw official runtime state every five minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=20s
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now openclaw-official-runtime-shadow.timer
systemctl start openclaw-official-runtime-shadow.service

AFTER=$(sha256sum "$JOBS" | awk '{print $1}')
test "$BEFORE" = "$AFTER"
systemctl is-enabled openclaw-cron-failure-self-heal.timer >/dev/null
systemctl is-enabled openclaw-long-task-supervisor.timer >/dev/null
systemctl is-active openclaw.service >/dev/null
test -s "$STATE"
python3 - <<'PY'
import json
from pathlib import Path

cfg = json.loads(Path('config/openclaw/official_runtime_migration.json').read_text())
state = json.loads(Path('/var/lib/openclaw/.openclaw/workspace/agent_society_kernel/official_runtime_shadow.json').read_text())
assert cfg['test_delivery_policy'] == 'owner_dm_only'
assert cfg['public_test_delivery_forbidden'] is True
assert set(cfg['owner_discord_dm_channel_ids']).isdisjoint(cfg['public_discord_channel_ids'])
assert state['mutations_performed'] is False
assert state['delivery_performed'] is False
assert state['cron_integrity']['changed_during_probe'] is False
print('OFFICIAL_RUNTIME_SHADOW_OK')
PY
'''


def main() -> int:
    password = load_openclaw_ssh_password()
    if not password:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    try:
        import paramiko
    except ImportError:
        print("paramiko is required for remote install", file=sys.stderr)
        return 1
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=password, timeout=90, allow_agent=False, look_for_keys=False)
    env = f"export SPRINGMONKEY_REPO_PATH={REPO!r}\n"
    _, stdout, stderr = client.exec_command(env + REMOTE, get_pty=True, timeout=900)
    output = stdout.read().decode("utf-8", errors="replace")
    error = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.write(output)
    if error.strip():
        sys.stderr.write(error)
    return 0 if "OFFICIAL_RUNTIME_SHADOW_OK" in output else 1


if __name__ == "__main__":
    raise SystemExit(main())
