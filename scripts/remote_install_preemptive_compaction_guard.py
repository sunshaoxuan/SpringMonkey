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
LOCAL_PATCH = _SCRIPTS / "openclaw" / "patch_preemptive_compaction_runtime_current.py"
REMOTE_PATCH = "/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw/patch_preemptive_compaction_runtime_current.py"

REMOTE = r"""
set -euo pipefail

python3 <<'PY'
from pathlib import Path
from datetime import datetime
import json
import shutil

cfg_path = Path("/var/lib/openclaw/.openclaw/openclaw.json")
cfg_backup = cfg_path.with_name(f"openclaw.json.bak-compaction-guard-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
shutil.copy2(cfg_path, cfg_backup)
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
comp = cfg.setdefault("agents", {}).setdefault("defaults", {}).setdefault("compaction", {})
comp["mode"] = "safeguard"
comp["reserveTokens"] = 12000
comp["keepRecentTokens"] = 8000
comp["reserveTokensFloor"] = 12000
comp["recentTurnsPreserve"] = 6
cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"CONFIG_BACKUP {cfg_backup}")
PY

REPO=/var/lib/openclaw/repos/SpringMonkey
PATCH="${REPO}/scripts/openclaw/patch_preemptive_compaction_runtime_current.py"
if [ ! -f "$PATCH" ]; then
  echo "missing patch script: $PATCH" >&2
  exit 1
fi

python3 "$PATCH"

systemctl restart openclaw.service
sleep 12
systemctl is-active openclaw.service
curl -fsS http://127.0.0.1:18789/healthz >/dev/null
curl -fsS http://127.0.0.1:18789/line/webhook >/dev/null
python3 <<'PY'
from pathlib import Path
dist = Path("/usr/lib/node_modules/openclaw/dist")
candidates = sorted(
    [p for p in dist.glob("selection-*.js") if p.is_file()],
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if not candidates:
    raise SystemExit("selection bundle not found during verification")
text = candidates[0].read_text(encoding="utf-8")
checks = {
    "proactive_threshold": "const proactiveThresholdTokens = Math.max(1, Math.floor(promptBudgetBeforeReserve * .82));" in text,
    "proactive_message_threshold": "const proactiveMessageThreshold = 48;" in text,
    "proactive_route": 'else if (params.messages.length >= proactiveMessageThreshold && estimatedPromptTokens >= proactiveThresholdTokens) route = "compact_only";' in text,
}
print(checks)
PY
python3 <<'PY'
import json
from pathlib import Path
cfg = json.loads(Path("/var/lib/openclaw/.openclaw/openclaw.json").read_text(encoding="utf-8"))
print(json.dumps(cfg["agents"]["defaults"]["compaction"], ensure_ascii=False, indent=2))
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
    sftp = client.open_sftp()
    try:
        try:
            sftp.mkdir("/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw")
        except OSError:
            pass
        sftp.put(str(LOCAL_PATCH), REMOTE_PATCH)
    finally:
        sftp.close()
    _, stdout, stderr = client.exec_command(REMOTE.strip(), get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    return 0 if "active" in out and "proactive_threshold" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
