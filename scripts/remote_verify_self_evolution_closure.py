#!/usr/bin/env python3
"""Remote end-to-end closure check for TangHou self-evolution runs."""
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

echo "=== self-evolution closure ==="
python3 scripts/openclaw/verify_self_evolution_closure.py --fetch

echo "=== registry ==="
python3 scripts/openclaw/verify_intent_tool_registry.py
python3 scripts/openclaw/verify_harness_registry.py
python3 scripts/openclaw/verify_capability_baseline.py | tail -n 20

echo "=== long task status ==="
HOME=/var/lib/openclaw python3 scripts/openclaw/long_task_supervisor.py status --limit 8

echo "SELF_EVOLUTION_CLOSURE_REMOTE_OK"
"""


def main() -> int:
    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    try:
        import paramiko
    except ImportError:
        print("paramiko is required for remote verification", file=sys.stderr)
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
    return 0 if "self_evolution_closure_ok" in out and "SELF_EVOLUTION_CLOSURE_REMOTE_OK" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
