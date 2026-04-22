#!/usr/bin/env python3
"""SSH 到汤猴宿主机，安装 agent society runtime 启动级自愈守护。"""
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
LOCAL_PATCH = _SCRIPTS / "openclaw" / "patch_agent_society_runtime_current.py"
REMOTE_PATCH = "/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw/patch_agent_society_runtime_current.py"

REMOTE = r"""
set -e
install -d -m 755 /usr/local/lib/openclaw
install -d -m 755 /etc/systemd/system/openclaw.service.d
cat >/usr/local/lib/openclaw/ensure_agent_society_runtime_guard.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
export HOME=/var/lib/openclaw
REPO=/var/lib/openclaw/repos/SpringMonkey
PATCH="${REPO}/scripts/openclaw/patch_agent_society_runtime_current.py"
if [ ! -f "$PATCH" ]; then
  echo "[agent-society-guard] missing patch script: $PATCH" >&2
  exit 1
fi
python3 "$PATCH" >/tmp/agent-society-runtime-guard.log 2>&1 || {
  cat /tmp/agent-society-runtime-guard.log >&2 || true
  exit 1
}
python3 - <<'PY'
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
    raise SystemExit("[agent-society-guard] runtime bundle not found after patch")
text = candidates[0].read_text(encoding="utf-8")
required = [
    "[runtime-goal-intent-task-agent-society-protocol]",
    "shouldApplyAgentSocietyProtocol",
    "extract all relevant intents",
    "create or refine a helper tool",
]
missing = [item for item in required if item not in text]
if missing:
    raise SystemExit(f"[agent-society-guard] patched bundle verification failed: missing {missing}")
workspace = Path("/var/lib/openclaw/.openclaw/workspace/AGENT_SOCIETY_RUNTIME.md")
if not workspace.exists():
    raise SystemExit("[agent-society-guard] workspace bridge file missing")
print("[agent-society-guard] patch verification ok")
PY
EOF
chmod 755 /usr/local/lib/openclaw/ensure_agent_society_runtime_guard.sh

cat >/etc/systemd/system/openclaw.service.d/30-agent-society-runtime-guard.conf <<'EOF'
[Service]
ExecStartPre=/usr/local/lib/openclaw/ensure_agent_society_runtime_guard.sh
EOF

systemctl daemon-reload
systemctl restart openclaw.service
sleep 12
systemctl is-active openclaw.service
echo "=== drop-in ==="
systemctl cat openclaw.service | sed -n '/30-agent-society-runtime-guard.conf/,+8p'
echo "=== patch verify ==="
/usr/local/lib/openclaw/ensure_agent_society_runtime_guard.sh
echo "=== recent logs ==="
journalctl -u openclaw.service -n 80 --no-pager | grep -E 'agent-society-guard|gateway] ready' || true
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
            "  python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt\n"
            "说明：SpringMonkey/docs/ops/SSH_TOOLCHAIN.md",
            file=sys.stderr,
        )
        return 1

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        HOST,
        port=PORT,
        username=USER,
        password=pw,
        timeout=60,
        allow_agent=False,
        look_for_keys=False,
    )
    if not LOCAL_PATCH.is_file():
        print(f"missing local patch script: {LOCAL_PATCH}", file=sys.stderr)
        c.close()
        return 1
    sftp = c.open_sftp()
    try:
        try:
            sftp.mkdir("/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw")
        except OSError:
            pass
        sftp.put(str(LOCAL_PATCH), REMOTE_PATCH)
    finally:
        sftp.close()
    stdin, stdout, stderr = c.exec_command(REMOTE, get_pty=True, timeout=900)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    c.close()
    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
