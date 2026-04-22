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
LOCAL_KERNEL = _SCRIPTS / "openclaw" / "agent_society_kernel.py"
REMOTE_KERNEL = "/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw/agent_society_kernel.py"

REMOTE = r"""
set -euo pipefail

WORKSPACE=/var/lib/openclaw/.openclaw/workspace
STATE_ROOT="${WORKSPACE}/agent_society_kernel"
mkdir -p "${STATE_ROOT}/sessions"
cat >"${WORKSPACE}/AGENT_SOCIETY_KERNEL.md" <<'EOF'
# Agent Society Kernel

This host has a minimal durable kernel for goal -> intent -> task -> step execution state.

State root:

- `/var/lib/openclaw/.openclaw/workspace/agent_society_kernel`

Current expectations:

- direct work may be represented as one goal with multiple intents
- intents may map to multiple tasks
- tasks map to concrete observable steps
- each step should identify current tool candidates and one chosen tool
- observations should be written back into durable state instead of living only in prompt text

Current limitation:

- this kernel is a state and execution-loop foundation
- it is not yet a full native OpenClaw scheduler
EOF

python3 "${REPO:-/var/lib/openclaw/repos/SpringMonkey}/scripts/openclaw/agent_society_kernel.py" \
  --root "${STATE_ROOT}" \
  new-session \
  --channel system \
  --user-id bootstrap \
  --prompt "bootstrap agent society kernel and verify durable goal intent task step state"
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

    if not LOCAL_KERNEL.is_file():
        print(f"missing local kernel script: {LOCAL_KERNEL}", file=sys.stderr)
        return 1

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=120, allow_agent=False, look_for_keys=False)
    sftp = client.open_sftp()
    try:
        try:
            sftp.mkdir("/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw")
        except OSError:
            pass
        sftp.put(str(LOCAL_KERNEL), REMOTE_KERNEL)
    finally:
        sftp.close()
    _, stdout, stderr = client.exec_command(REMOTE.strip(), get_pty=True, timeout=180)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    return 0 if "\"session_id\"" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
