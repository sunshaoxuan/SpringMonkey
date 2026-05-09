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
cd "$REPO"
git pull --ff-only
python3 scripts/openclaw/patch_discord_gateway_ready_final.py
python3 scripts/openclaw/patch_discord_gateway_ready_fast_state.py
python3 scripts/openclaw/patch_discord_message_create_diagnostics.py
systemctl restart openclaw.service
sleep 35
systemctl is-active openclaw.service
journalctl -u openclaw.service --since '2 minutes ago' --no-pager | egrep -i 'discord gateway READY confirmed|springmonkey message create|discord message diag|awaiting gateway readiness|did not reach READY|gateway was not ready|liveness warning' | tail -160
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
        print("缺少 paramiko。请执行：python -m pip install -r scripts/requirements-ssh.txt", file=sys.stderr)
        return 1
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=120, allow_agent=False, look_for_keys=False)
    _, stdout, stderr = client.exec_command(REMOTE.strip(), get_pty=True, timeout=360)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
    if err.strip():
        sys.stderr.buffer.write(err.encode("utf-8", errors="replace"))
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
