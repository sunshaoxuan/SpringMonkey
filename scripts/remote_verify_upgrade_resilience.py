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

REMOTE = r"""
set -euo pipefail
export HOME=/var/lib/openclaw
cd "$SPRINGMONKEY_REPO_PATH"
echo "=== versions ==="
openclaw --version
node --version
echo "=== service ==="
systemctl is-active openclaw.service
echo "=== health ==="
python3 - <<'PY'
import json
import urllib.request
with urllib.request.urlopen("http://127.0.0.1:18789/healthz", timeout=8) as resp:
    payload = resp.read().decode("utf-8", errors="replace")
print(payload)
data = json.loads(payload)
if data.get("ok") is not True:
    raise SystemExit("healthz not ok")
PY
echo "=== runtime patch inventory ==="
python3 scripts/openclaw/runtime_patch_inventory.py --fail-on-missing
echo "=== guards ==="
test -x /usr/local/lib/openclaw/ensure_agent_society_runtime_guard.sh
test -x /usr/local/lib/openclaw/ensure_memory_lancedb_guard.sh
systemctl is-enabled openclaw-long-task-supervisor.timer >/dev/null
systemctl list-timers openclaw-long-task-supervisor.timer --no-pager || true
echo "=== registry ==="
python3 scripts/openclaw/verify_intent_tool_registry.py
python3 scripts/openclaw/verify_harness_registry.py
python3 scripts/openclaw/verify_capability_baseline.py
echo "UPGRADE_RESILIENCE_OK"
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
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=90, allow_agent=False, look_for_keys=False)
    env = f"export SPRINGMONKEY_REPO_PATH={REPO!r}\n"
    _, stdout, stderr = client.exec_command(env + REMOTE, get_pty=True, timeout=600)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    return 0 if "UPGRADE_RESILIENCE_OK" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
