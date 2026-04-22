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
USER = "root"
LOCAL_PATCH = _SCRIPTS / "openclaw" / "patch_agent_society_runtime_current.py"
REMOTE_PATCH = "/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw/patch_agent_society_runtime_current.py"
LOCAL_PREEMPTIVE_PATCH = _SCRIPTS / "openclaw" / "patch_preemptive_compaction_runtime_current.py"
REMOTE_PREEMPTIVE_PATCH = "/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw/patch_preemptive_compaction_runtime_current.py"
LOCAL_KERNEL = _SCRIPTS / "openclaw" / "agent_society_kernel.py"
REMOTE_KERNEL = "/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw/agent_society_kernel.py"

REMOTE = r"""
set -euo pipefail

REPO=/var/lib/openclaw/repos/SpringMonkey
PATCH="${REPO}/scripts/openclaw/patch_agent_society_runtime_current.py"
PREEMPTIVE_PATCH="${REPO}/scripts/openclaw/patch_preemptive_compaction_runtime_current.py"
KERNEL="${REPO}/scripts/openclaw/agent_society_kernel.py"
if [ ! -f "$PATCH" ]; then
  echo "missing patch script: $PATCH" >&2
  exit 1
fi
if [ ! -f "$PREEMPTIVE_PATCH" ]; then
  echo "missing patch script: $PREEMPTIVE_PATCH" >&2
  exit 1
fi
if [ ! -f "$KERNEL" ]; then
  echo "missing kernel script: $KERNEL" >&2
  exit 1
fi

python3 "$PATCH"
python3 "$PREEMPTIVE_PATCH"
install -d -m 755 /var/lib/openclaw/.openclaw/workspace/agent_society_kernel/sessions
python3 "$KERNEL" --root /var/lib/openclaw/.openclaw/workspace/agent_society_kernel new-session --channel system --user-id bootstrap --prompt "refresh agent society kernel state root after runtime deployment" >/tmp/agent-society-kernel-bootstrap.log 2>&1 || {
  cat /tmp/agent-society-kernel-bootstrap.log >&2 || true
  exit 1
}

systemctl restart openclaw.service
systemctl is-active openclaw.service
python3 <<'PY'
import time
from urllib.request import urlopen

last_error = "unknown"
for _ in range(40):
    try:
        with urlopen("http://127.0.0.1:18789/healthz", timeout=3) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
        print("HEALTH_OK", payload)
        raise SystemExit(0)
    except Exception as exc:
        last_error = str(exc)
        time.sleep(2)
print(f"HEALTH_FAIL {last_error}")
raise SystemExit(1)
PY
python3 <<'PY'
from pathlib import Path
dist = Path("/usr/lib/node_modules/openclaw/dist")
candidates = sorted(
    [
        p
        for p in dist.glob("agent-runner.runtime-*.js")
        if p.name != "agent-runner.runtime.js" and p.is_file()
    ],
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if not candidates:
    raise SystemExit("runtime bundle not found during verification")
text = candidates[0].read_text(encoding="utf-8")
checks = {
    "agent_society_protocol_token": "[runtime-goal-intent-task-agent-society-protocol]" in text,
    "agent_society_guard": "shouldApplyAgentSocietyProtocol" in text,
    "multi_intent_rule": "extract all relevant intents" in text,
    "tool_ecology_rule": "create or refine a helper tool" in text,
    "self_improvement_rule": "[runtime-self-improvement-toolsmith-protocol]" in text,
    "capability_gap_rule": "classify the failure into a capability gap" in text,
}
print(checks)
selection_candidates = sorted(
    [p for p in dist.glob("selection-*.js") if p.is_file()],
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if not selection_candidates:
    raise SystemExit("selection bundle not found during verification")
selection_text = selection_candidates[0].read_text(encoding="utf-8")
print({
    "preemptive_compaction_guard": "const proactiveThresholdTokens = Math.max(1, Math.floor(promptBudgetBeforeReserve * .9));" in selection_text,
    "preemptive_message_threshold": "const proactiveMessageThreshold = 48;" in selection_text,
})
workspace_file = Path("/var/lib/openclaw/.openclaw/workspace/AGENT_SOCIETY_RUNTIME.md")
print({"workspace_policy": workspace_file.exists()})
kernel_workspace = Path("/var/lib/openclaw/.openclaw/workspace/AGENT_SOCIETY_KERNEL.md")
kernel_state_root = Path("/var/lib/openclaw/.openclaw/workspace/agent_society_kernel")
print({
    "kernel_workspace_policy": kernel_workspace.exists(),
    "kernel_state_root": kernel_state_root.exists(),
    "kernel_sessions_dir": (kernel_state_root / "sessions").exists(),
})
PY
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

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=120, allow_agent=False, look_for_keys=False)
    if not LOCAL_PATCH.is_file():
        print(f"missing local patch script: {LOCAL_PATCH}", file=sys.stderr)
        client.close()
        return 1
    if not LOCAL_PREEMPTIVE_PATCH.is_file():
        print(f"missing local patch script: {LOCAL_PREEMPTIVE_PATCH}", file=sys.stderr)
        client.close()
        return 1
    if not LOCAL_KERNEL.is_file():
        print(f"missing local kernel script: {LOCAL_KERNEL}", file=sys.stderr)
        client.close()
        return 1
    sftp = client.open_sftp()
    try:
        try:
            sftp.mkdir("/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw")
        except OSError:
            pass
        sftp.put(str(LOCAL_PATCH), REMOTE_PATCH)
        sftp.put(str(LOCAL_PREEMPTIVE_PATCH), REMOTE_PREEMPTIVE_PATCH)
        sftp.put(str(LOCAL_KERNEL), REMOTE_KERNEL)
    finally:
        sftp.close()
    _, stdout, stderr = client.exec_command(REMOTE.strip(), get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    return 0 if "HEALTH_OK" in out and "agent_society_protocol_token" in out and "preemptive_compaction_guard" in out and "kernel_state_root" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
