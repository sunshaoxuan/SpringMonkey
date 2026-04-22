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
KERNEL="${REPO}/scripts/openclaw/agent_society_kernel.py"
TOOLSMITH="${REPO}/scripts/openclaw/agent_society_helper_toolsmith.py"
if [ ! -f "$KERNEL" ]; then
  echo "missing kernel script: $KERNEL" >&2
  exit 1
fi
if [ ! -f "$TOOLSMITH" ]; then
  echo "missing toolsmith script: $TOOLSMITH" >&2
  exit 1
fi
install -d -m 755 /var/lib/openclaw/.openclaw/workspace/agent_society_kernel/sessions
install -d -m 755 /var/lib/openclaw/.openclaw/workspace/agent_society_kernel/runtime
cat >/var/lib/openclaw/.openclaw/workspace/agent_society_kernel/runtime/README.md <<'EOF'
# Agent Society Kernel Bridge

This bridge exists so direct tasks can be mirrored into durable kernel state.

Current bridge expectations:

- create or reuse a kernel session for a direct task
- classify repeated failures into durable capability gaps
- generate bounded helper-tool scaffolds in the repo when a reusable gap is detected
- reuse validated helper entrypoints as preferred tool candidates on later steps
EOF
python3 "$KERNEL" --root /var/lib/openclaw/.openclaw/workspace/agent_society_kernel ensure-session --channel system --user-id bridge-bootstrap --prompt "bootstrap direct-task kernel bridge"
"""


def main() -> int:
    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    try:
        import paramiko
    except ImportError:
        print("缺少 paramiko。请执行一次：\n  python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt", file=sys.stderr)
        return 1
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=120, allow_agent=False, look_for_keys=False)
    _, stdout, stderr = client.exec_command(REMOTE, get_pty=True, timeout=300)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    return 0 if "session_id" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
