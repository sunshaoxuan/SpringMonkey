#!/usr/bin/env python3
"""SSH 到汤猴宿主机，拉起常驻 Chrome CDP backend 并接到 OpenClaw raw CDP profile。"""
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

install -d -m 755 /usr/local/lib/openclaw
install -d -m 755 /var/lib/openclaw/browser-profile/openclaw
chown -R openclaw:openclaw /var/lib/openclaw/browser-profile

cat >/usr/local/lib/openclaw/start_persistent_browser.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
export HOME=/var/lib/openclaw
export DISPLAY=:99
PROFILE_DIR=/var/lib/openclaw/browser-profile/openclaw
XVFB_PID=""

cleanup() {
  if [ -n "${CHROME_PID:-}" ]; then kill "${CHROME_PID}" 2>/dev/null || true; fi
  if [ -n "$XVFB_PID" ]; then kill "$XVFB_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT

if ! pgrep -f "Xvfb :99" >/dev/null 2>&1; then
  Xvfb :99 -screen 0 1280x720x24 -nolisten tcp >/tmp/openclaw-xvfb.log 2>&1 &
  XVFB_PID=$!
  sleep 2
fi

exec /usr/bin/google-chrome \
  --user-data-dir="${PROFILE_DIR}" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=18800 \
  --no-first-run \
  --no-default-browser-check \
  --disable-background-networking \
  --disable-sync \
  --disable-component-update \
  --disable-dev-shm-usage \
  --password-store=basic \
  --new-window \
  about:blank
EOF
chmod 755 /usr/local/lib/openclaw/start_persistent_browser.sh

cat >/etc/systemd/system/openclaw-browser-backend.service <<'EOF'
[Unit]
Description=Persistent Chrome CDP backend for OpenClaw
After=network-online.target

[Service]
Type=simple
User=openclaw
Environment=HOME=/var/lib/openclaw
ExecStart=/usr/local/lib/openclaw/start_persistent_browser.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

python3 <<'PY'
import json
import shutil
from datetime import datetime
from pathlib import Path
p = Path("/var/lib/openclaw/.openclaw/openclaw.json")
ts = datetime.now().strftime("%Y%m%d-%H%M%S")
bak = p.with_name(f"openclaw.json.bak-persistent-browser-{ts}")
shutil.copy2(p, bak)
d = json.loads(p.read_text(encoding="utf-8"))
b = d.setdefault("browser", {})
b["enabled"] = True
b["defaultProfile"] = "openclaw"
b["executablePath"] = "/usr/bin/google-chrome"
profiles = b.setdefault("profiles", {})
profiles["openclaw"] = {
    "cdpPort": 18800,
    "color": "#FF4500",
}
p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(str(bak))
PY

systemctl daemon-reload
systemctl enable --now openclaw-browser-backend.service
sleep 8
systemctl restart openclaw.service
sleep 8
systemctl is-active openclaw-browser-backend.service
ss -ltnp | grep 18800 || true
curl -sS http://127.0.0.1:18800/json/version || true
sudo -u openclaw env HOME=/var/lib/openclaw bash -lc 'timeout 30 openclaw browser status || true; echo ---; timeout 30 openclaw browser profiles || true'
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
