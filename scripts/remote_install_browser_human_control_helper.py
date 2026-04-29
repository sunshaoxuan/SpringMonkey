#!/usr/bin/env python3
"""Deploy and promote the host Chrome CDP human-control helper."""
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

REMOTE = r"""
set -euo pipefail
export HOME=/var/lib/openclaw
REPO=${SPRINGMONKEY_REPO_PATH:-/var/lib/openclaw/repos/SpringMonkey}
KERNEL_ROOT=/var/lib/openclaw/.openclaw/workspace/agent_society_kernel
HELPER="$REPO/scripts/openclaw/helpers/browser_cdp_human.py"

if [ ! -f "$HELPER" ]; then
  echo "missing helper after repo sync: $HELPER" >&2
  exit 1
fi

chmod 755 "$HELPER" || true

python3 "$HELPER" status >/tmp/browser-cdp-human-status.json
python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path("/tmp/browser-cdp-human-status.json").read_text(encoding="utf-8"))
if not payload.get("ok"):
    raise SystemExit("browser_cdp_human status did not return ok")
if payload.get("headlessLike"):
    raise SystemExit("persistent Chrome looks headless-like; refusing to promote helper")
print(json.dumps({
    "status": "ready",
    "browser": payload.get("browser"),
    "headlessLike": payload.get("headlessLike"),
    "tabCount": len(payload.get("tabs") or []),
}, ensure_ascii=False))
PY

python3 <<'PY'
import json
import sys
from pathlib import Path

repo = Path("/var/lib/openclaw/repos/SpringMonkey")
sys.path.insert(0, str(repo / "scripts" / "openclaw"))
from agent_society_kernel import AgentSocietyKernel

kernel = AgentSocietyKernel(Path("/var/lib/openclaw/.openclaw/workspace/agent_society_kernel"))
session = kernel.bootstrap_session(
    "Browser targetId/tab drift while using persistent host Chrome; promote CDP human-control helper.",
    channel="system",
    user_id="browser-human-control-installer",
)
step = kernel.next_step(session)
if step is None:
    raise SystemExit("kernel did not produce a step")
gap = kernel.analyze_capability_gap(
    session,
    step.step_id,
    "browser failed: action targetId must match request targetId; tab not found; fill requires fields; incorrect headless fallback/profile=user advice",
)
session = kernel.load_session(session.session_id)
tool = kernel.propose_helper_from_gap(
    session,
    gap.gap_id,
    "script",
    "scripts/openclaw/helpers/browser_cdp_human.py",
    scope="browser_control",
    notes=gap.proposed_repair,
)
validation = {
    "status": "ready",
    "contract": {
        "helper_name": "browser_cdp_human",
        "category": "browser_control",
        "purpose": "Use persistent host Chrome through raw CDP when OpenClaw browser target/ref mapping drifts.",
    },
    "repair_workflow": [
        {"step": "prove browser substrate", "action": "run browser_cdp_human.py status and verify headlessLike=false"},
        {"step": "reselect live target", "action": "inspect /json/list and choose a live non-blank CDP target before every action"},
        {"step": "act through CDP fallback", "action": "use open/inspect/click/type/wait-text commands instead of stale browser targetId/ref values"},
        {"step": "report real blocker", "action": "return current URL and page text when site validation, CAPTCHA, phone verification, or policy block appears"},
    ],
    "drift": {"ok": True, "reasons": []},
}
session = kernel.load_session(session.session_id)
kernel.validate_helper_tool(session, tool.tool_id, json.dumps(validation, ensure_ascii=False), "promoted")
print(json.dumps({
    "promoted": True,
    "entrypoint": "scripts/openclaw/helpers/browser_cdp_human.py",
    "scope": "browser_control",
}, ensure_ascii=False))
PY

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
        print(
            "缺少 paramiko。请执行一次：\n"
            "  python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt",
            file=sys.stderr,
        )
        return 1
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=60, allow_agent=False, look_for_keys=False)
    _, stdout, stderr = client.exec_command(REMOTE.strip(), get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
    if err.strip():
        sys.stderr.buffer.write(err.encode("utf-8", errors="replace"))
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
