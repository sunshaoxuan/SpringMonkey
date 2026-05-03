#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint


HOST = os.environ.get("OPENCLAW_SSH_HOST", "ccnode.briconbric.com")
PORT = int(os.environ.get("OPENCLAW_SSH_PORT", "8822"))
USER = os.environ.get("OPENCLAW_SSH_USER", "root")
OWNER_DISCORD_USER_ID = os.environ.get("OPENCLAW_OWNER_DISCORD_USER_ID", "999666719356354610")

REMOTE = r"""
set -euo pipefail

REPO="/var/lib/openclaw/repos/SpringMonkey"
CONFIG="/var/lib/openclaw/.openclaw/openclaw.json"
OWNER="__OWNER_DISCORD_USER_ID__"

cd "$REPO"
git remote set-url origin https://github.com/sunshaoxuan/SpringMonkey.git
git pull --ff-only

# Remove the rejected polling fallback if it had been installed by an earlier hotfix.
systemctl disable --now openclaw-discord-dm-control.timer >/dev/null 2>&1 || true
rm -f /etc/systemd/system/openclaw-discord-dm-control.timer /etc/systemd/system/openclaw-discord-dm-control.service
systemctl daemon-reload

python3 <<'PY'
import json
import shutil
from datetime import datetime
from pathlib import Path

config = Path("/var/lib/openclaw/.openclaw/openclaw.json")
owner = "__OWNER_DISCORD_USER_ID__"
backup = config.with_name(f"openclaw.json.bak-discord-dm-event-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
shutil.copy2(config, backup)

data = json.loads(config.read_text(encoding="utf-8"))
discord = data.setdefault("channels", {}).setdefault("discord", {})

# Event-driven DM handling must pass OpenClaw's own Discord preflight.
# Use an owner-only allowlist instead of dmPolicy=open + wildcard access.
discord["dmPolicy"] = "allowlist"
allow_from = [str(item) for item in discord.get("allowFrom", []) if str(item).strip()]
if owner not in allow_from:
    allow_from.append(owner)
discord["allowFrom"] = allow_from

# Keep the public guild/channel allowlist unchanged.
config.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(
    {
        "backup": str(backup),
        "dmPolicy": discord.get("dmPolicy"),
        "allowFrom": discord.get("allowFrom"),
        "groupPolicy": discord.get("groupPolicy"),
    },
    ensure_ascii=False,
    indent=2,
))
PY

systemctl restart openclaw.service
sleep 8
systemctl is-active openclaw.service

python3 <<'PY'
import json
from pathlib import Path

data = json.loads(Path("/var/lib/openclaw/.openclaw/openclaw.json").read_text(encoding="utf-8"))
discord = data.get("channels", {}).get("discord", {})
print(json.dumps(
    {
        "dmPolicy": discord.get("dmPolicy"),
        "allowFrom": discord.get("allowFrom"),
        "groupPolicy": discord.get("groupPolicy"),
        "dmControlPoller": "removed",
    },
    ensure_ascii=False,
    indent=2,
))
PY

echo DONE
""".replace("__OWNER_DISCORD_USER_ID__", OWNER_DISCORD_USER_ID)


def main() -> int:
    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    try:
        import paramiko
    except ImportError:
        print("缺少 paramiko。请执行：python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt", file=sys.stderr)
        return 1
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=120, allow_agent=False, look_for_keys=False)
    _, stdout, stderr = client.exec_command(REMOTE.strip(), get_pty=True, timeout=300)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
