#!/usr/bin/env python3
"""SSH 到汤猴宿主机，启用一批国际向官方渠道插件并预注册配置入口。"""
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

CHANNELS="telegram slack whatsapp signal msteams mattermost googlechat irc synology-chat"

python3 <<'PY'
import json
import shutil
from datetime import datetime
from pathlib import Path

channels = "telegram slack whatsapp signal msteams mattermost googlechat irc synology-chat".split()
p = Path("/var/lib/openclaw/.openclaw/openclaw.json")
ts = datetime.now().strftime("%Y%m%d-%H%M%S")
bak = p.with_name(f"openclaw.json.bak-international-channels-{ts}")
shutil.copy2(p, bak)
d = json.loads(p.read_text(encoding="utf-8"))
plugins = d.setdefault("plugins", {})
allow = plugins.setdefault("allow", [])
entries = plugins.setdefault("entries", {})
cfg_channels = d.setdefault("channels", {})

# Preserve core plugins that are already part of the running host baseline.
for core in ("line", "discord", "diagnostics-otel", "diffs", "llm-task", "lobster", "browser"):
    if core not in allow:
        allow.append(core)

for ch in channels:
    if ch not in allow:
        allow.append(ch)
    entry = entries.setdefault(ch, {})
    entry["enabled"] = True
    channel_cfg = cfg_channels.setdefault(ch, {})
    channel_cfg.setdefault("enabled", False)
    channel_cfg.setdefault("dmPolicy", "pairing")
    channel_cfg.setdefault("groupPolicy", "allowlist")

# These stock plugins are present in this host build but should stay disabled:
# nextcloud-talk / nostr fail export validation;
# matrix blocks CLI bootstrap on this host build;
# twitch requires additional schema the current runtime does not accept.
for broken in ("nextcloud-talk", "nostr", "matrix", "twitch"):
    if broken in allow:
        allow.remove(broken)
    entries.pop(broken, None)
    cfg_channels.pop(broken, None)

p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"backup": str(bak), "channels": channels}, ensure_ascii=False, indent=2))
PY

for ch in $CHANNELS; do
  sudo -u openclaw env HOME=/var/lib/openclaw bash -lc "openclaw plugins enable '$ch' >/dev/null 2>&1 || true"
  sudo -u openclaw env HOME=/var/lib/openclaw bash -lc "openclaw channels add --channel '$ch' >/dev/null 2>&1 || true"
done

systemctl restart openclaw.service
sleep 8
systemctl is-active openclaw.service

sudo -u openclaw env HOME=/var/lib/openclaw bash -lc 'openclaw plugins list' | grep -E 'telegram|slack|whatsapp|signal|msteams|mattermost|googlechat|matrix|nextcloud-talk|nostr|irc|twitch|synology-chat' || true
echo "===== channels ====="
sudo -u openclaw env HOME=/var/lib/openclaw bash -lc 'openclaw channels list' || true
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

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=pw, timeout=60, allow_agent=False, look_for_keys=False)
    _, so, se = c.exec_command(REMOTE.strip(), get_pty=True)
    out = so.read().decode("utf-8", errors="replace")
    err = se.read().decode("utf-8", errors="replace")
    c.close()
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
    if err.strip():
        sys.stderr.buffer.write(err.encode("utf-8", errors="replace"))
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
