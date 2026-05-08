#!/usr/bin/env python3
"""Remote smoke validation for semantic read-only toolsmith repairs."""
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
set -uo pipefail
cd "$SPRINGMONKEY_REPO_PATH" || exit 1
TMP_KERNEL="$(mktemp -d /tmp/openclaw-toolsmith-semantic.XXXXXX)"

echo "=== git ==="
git rev-parse --short HEAD
git status --short

echo "=== service ==="
systemctl is-active openclaw.service || true

echo "=== memory plugin ==="
openclaw plugins inspect memory-lancedb 2>&1 | sed -n '1,80p' || true

echo "=== registry verify ==="
python scripts/openclaw/verify_intent_tool_registry.py
python scripts/openclaw/verify_harness_registry.py

echo "=== semantic package ==="
python scripts/openclaw/toolsmith_repair_runner.py \
  --text "请查询小红书长记忆里 Frutteto 投稿记录" \
  --reason "no registered tool for readonly memory lookup" \
  --safety-class auto_safe_readonly \
  --kernel-root "$TMP_KERNEL" \
  --repo-root "$PWD" \
  --semantic 2>&1 | tee /tmp/openclaw-toolsmith-semantic-package.json

echo "=== semantic assertions ==="
python - <<'PY'
import json
from pathlib import Path
raw = Path("/tmp/openclaw-toolsmith-semantic-package.json").read_text(encoding="utf-8", errors="replace")
start = raw.find("{")
payload = json.loads(raw[start:])
assert payload["status"] == "generated", payload
assert payload["registry_patch"]["implementation_status"] == "ready", payload
assert payload["semantic_source"], payload
helper = Path(payload["files"][0])
assert helper.is_file(), helper
text = helper.read_text(encoding="utf-8", errors="replace")
assert '"status": "draft"' not in text
assert "semantic_helper" in text
print("semantic_toolsmith_ok", payload["tool_id"], payload["semantic_source"])
PY

echo "=== ltm search smoke ==="
openclaw ltm search "小红书 Costco Frutteto 投稿" --limit 3 2>&1 | sed -n '1,120p' || true

echo "=== self evolution status ==="
python scripts/openclaw/self_evolution_status.py --limit 5 || true

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
    return 0 if "DONE" in out and "semantic_toolsmith_ok" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
