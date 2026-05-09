#!/usr/bin/env python3
"""Remote smoke validation for the generic long-task supervisor."""
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
STATE="$(mktemp /tmp/openclaw-long-task-state.XXXXXX.json)"
SESSIONS="$(mktemp -d /tmp/openclaw-long-task-sessions.XXXXXX)"

echo "=== git ==="
git rev-parse --short HEAD
git status --short

echo "=== service ==="
systemctl is-active openclaw.service

echo "=== registry ==="
python scripts/openclaw/verify_intent_tool_registry.py
python scripts/openclaw/verify_harness_registry.py
python scripts/openclaw/verify_capability_baseline.py | tail -n 20

echo "=== supervisor register ==="
python scripts/openclaw/long_task_supervisor.py --state "$STATE" --sessions-dir "$SESSIONS" register \
  --source cron --job-id job_remote_smoke --run-id run_remote_smoke --job-name remote-smoke \
  --original-text "remote long task smoke" --timeout-seconds 600

echo "=== fake final session ==="
python - "$SESSIONS" <<'PY'
import json, sys
from pathlib import Path
sessions = Path(sys.argv[1])
(sessions / "run.jsonl").write_text(
    "agent:main:cron:job_remote_smoke:run:run_remote_smoke\n"
    + json.dumps({
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "remote final ok", "textSignature": "{\"phase\":\"final_answer\"}"}],
        }
    }, ensure_ascii=False),
    encoding="utf-8",
)
PY

echo "=== supervisor poll ==="
python scripts/openclaw/long_task_supervisor.py --state "$STATE" --sessions-dir "$SESSIONS" poll --no-repair | tee /tmp/openclaw-long-task-poll.json
python - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/openclaw-long-task-poll.json").read_text(encoding="utf-8"))
task = data["tasks"][0]
assert task["status"] == "final_detected", task
assert task["final_report"] == "remote final ok", task
print("long_task_supervisor_remote_ok", task["task_id"])
PY

echo "=== status ==="
python scripts/openclaw/long_task_supervisor.py --state "$STATE" status --limit 5

rm -rf "$STATE" "$SESSIONS"
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
    return 0 if "long_task_supervisor_remote_ok" in out and "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
