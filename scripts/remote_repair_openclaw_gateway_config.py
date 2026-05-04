#!/usr/bin/env python3
"""
Repair OpenClaw gateway config startup blockers through the host checkout.

This script does not upload files over SSH. It expects the host to pull the
SpringMonkey repository, then runs the repository repair script in place.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint

HOST = "ccnode.briconbric.com"
PORT = 8822
USER = "root"

REMOTE = r"""
set -euo pipefail
REPO=/var/lib/openclaw/repos/SpringMonkey
cd "$REPO"
git fetch origin --prune
git checkout main
git pull --ff-only origin main
systemctl stop openclaw.service || true
python3 scripts/openclaw/repair_legacy_gateway_config.py
START_MARK=$(date '+%Y-%m-%d %H:%M:%S')
systemctl start openclaw.service
sleep 25
printf 'SERVICE='; systemctl is-active openclaw.service || true
printf '\nHEALTH='; curl -sS --max-time 10 http://127.0.0.1:18789/healthz || true
printf '\nRECENT\n'
journalctl -u openclaw.service --since "$START_MARK" --no-pager \
  | grep -Ei 'gateway|ready|discord|invalid config|failed|error|message run failed|SyntaxError|TypeError' \
  | tail -n 160 || true
echo
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
    client.connect(
        HOST,
        port=PORT,
        username=USER,
        password=password,
        timeout=90,
        allow_agent=False,
        look_for_keys=False,
    )
    try:
        _, stdout, stderr = client.exec_command(REMOTE, get_pty=True, timeout=240)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
    finally:
        client.close()

    print(out, end="")
    if err.strip():
        print(err, file=sys.stderr, end="")
    failed = (
        "DONE" not in out
        or "SERVICE=active" not in out
        or "Failed to connect" in out
        or "Invalid config" in out
        or "SyntaxError" in out
        or "TypeError" in out
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
