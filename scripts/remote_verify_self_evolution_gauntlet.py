#!/usr/bin/env python3
"""Remote controlled gauntlet for TangHou self-evolution closure."""
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

echo "=== git ==="
git rev-parse --short HEAD
git status --short

echo "=== service ==="
systemctl is-active openclaw.service

echo "=== readonly gauntlet ==="
TMP_KERNEL="$(mktemp -d /tmp/openclaw-gauntlet-kernel.XXXXXX)"
TMP_STATE="$(mktemp /tmp/openclaw-gauntlet-state.XXXXXX.json)"
python3 scripts/openclaw/self_evolution_gauntlet.py \
  --scenario readonly-helper-regression \
  --kernel-root "$TMP_KERNEL" \
  --state "$TMP_STATE" \
  --worktree-temp \
  --json | tee /tmp/openclaw-gauntlet-readonly.json
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/openclaw-gauntlet-readonly.json").read_text(encoding="utf-8"))
assert data["ok"] is True, data
assert data["status"] == "final_succeeded", data
assert data["commit"], data
assert data["changed_files"], data
print("readonly_gauntlet_ok", data["commit"][:12])
PY

echo "=== write gauntlet ==="
python3 scripts/openclaw/self_evolution_gauntlet.py \
  --scenario write-tool-regression \
  --kernel-root "$TMP_KERNEL" \
  --state "$TMP_STATE" \
  --worktree-temp \
  --json | tee /tmp/openclaw-gauntlet-write.json
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/openclaw-gauntlet-write.json").read_text(encoding="utf-8"))
assert data["ok"] is True, data
assert data["status"] == "final_succeeded", data
assert data["commit"], data
assert data["replay_allowed"] is False, data
print("write_gauntlet_ok", data["commit"][:12])
PY

echo "=== closure ==="
python3 scripts/openclaw/verify_self_evolution_closure.py --fetch --require-gauntlet --gauntlet-root "$TMP_KERNEL"

rm -rf "$TMP_KERNEL" "$TMP_STATE"
echo SELF_EVOLUTION_GAUNTLET_REMOTE_OK
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
    _, stdout, stderr = client.exec_command(env + REMOTE, get_pty=True, timeout=900)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    required = ["readonly_gauntlet_ok", "write_gauntlet_ok", "self_evolution_closure_ok", "SELF_EVOLUTION_GAUNTLET_REMOTE_OK"]
    return 0 if all(item in out for item in required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
