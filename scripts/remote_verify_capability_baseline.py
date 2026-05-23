#!/usr/bin/env python3
"""Remote smoke validation for the capability baseline and regression gate."""
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
cd "$SPRINGMONKEY_REPO_PATH"

echo "=== git ==="
git rev-parse --short HEAD
git status --short

echo "=== service ==="
systemctl is-active openclaw.service

echo "=== registry ==="
python scripts/openclaw/verify_intent_tool_registry.py
python scripts/openclaw/verify_harness_registry.py

echo "=== capability baseline ==="
python scripts/openclaw/verify_capability_baseline.py --fail-open-model

echo "=== regression package smoke ==="
TMP_KERNEL="$(mktemp -d /tmp/openclaw-regression-baseline.XXXXXX)"
python scripts/openclaw/regression_repair_runner.py \
  --text "把这单的开始时间往后推24小时，结束时间不变。" \
  --stage binding \
  --reason "tool binding gap" \
  --kernel-root "$TMP_KERNEL" | tee /tmp/openclaw-regression-baseline.json
python - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path("/tmp/openclaw-regression-baseline.json").read_text(encoding="utf-8"))
assert payload["matched"] is True, payload
assert payload["status"] == "internal_repair_required", payload
assert payload["expected_tool_id"] == "timescar.dm.adjust_start", payload
assert payload["write_operation"] is True, payload
assert payload["package"]["internal_repair_allowed"] is True, payload
assert payload["package"]["external_side_effect"] is True, payload
print("regression_gate_ok", payload["baseline_case_id"], payload["status"])
PY
rm -rf "$TMP_KERNEL"

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
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=90, allow_agent=False, look_for_keys=False)
    command = "\n".join([f"export SPRINGMONKEY_REPO_PATH={REPO!r}", REMOTE.strip()])
    _, stdout, stderr = client.exec_command(command, get_pty=True, timeout=600)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
    if err.strip():
        sys.stderr.buffer.write(err.encode("utf-8", errors="replace"))
    return 0 if "DONE" in out and "regression_gate_ok" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
