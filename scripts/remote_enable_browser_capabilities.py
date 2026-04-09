#!/usr/bin/env python3
"""SSH 到汤猴宿主机，修复 Node HTTPS 证书链并加固浏览器能力。"""
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
export DEBIAN_FRONTEND=noninteractive

install -d -m 755 /etc/openclaw
install -d -m 755 /var/lib/openclaw/browser-profile
chown -R openclaw:openclaw /var/lib/openclaw/browser-profile

if [ ! -f /etc/openclaw/openclaw.env ]; then
  install -m 640 -o root -g openclaw /dev/null /etc/openclaw/openclaw.env
fi

python3 <<'PY'
from pathlib import Path

p = Path("/etc/openclaw/openclaw.env")
lines = []
if p.exists():
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()

wanted = {
    "NODE_OPTIONS": "--use-openssl-ca",
    "NODE_EXTRA_CA_CERTS": "/etc/ssl/certs/ca-certificates.crt",
}
kept = []
seen = set()
for raw in lines:
    if "=" not in raw:
        kept.append(raw)
        continue
    key, _ = raw.split("=", 1)
    if key in wanted:
        if key not in seen:
            kept.append(f"{key}={wanted[key]}")
            seen.add(key)
    else:
        kept.append(raw)
for key, value in wanted.items():
    if key not in seen:
        kept.append(f"{key}={value}")
p.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")
print(p)
PY

python3 <<'PY'
import json
import shutil
from datetime import datetime
from pathlib import Path

p = Path("/var/lib/openclaw/.openclaw/openclaw.json")
ts = datetime.now().strftime("%Y%m%d-%H%M%S")
bak = p.with_name(f"openclaw.json.bak-browser-capabilities-{ts}")
shutil.copy2(p, bak)

d = json.loads(p.read_text(encoding="utf-8"))
b = d.setdefault("browser", {})
b["enabled"] = True
b["defaultProfile"] = "openclaw"
b["executablePath"] = "/usr/bin/google-chrome"
b.pop("launchOptions", None)

plugins = d.setdefault("plugins", {}).setdefault("entries", {}).setdefault("browser", {})
plugins["enabled"] = True
plugins.pop("config", None)

p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"backup": str(bak), "browser": b, "pluginBrowser": plugins}, ensure_ascii=False, indent=2))
PY

apt-get update
apt-get install -y xvfb xauth
npm install -g playwright

systemctl daemon-reload
systemctl restart openclaw.service
sleep 8
systemctl is-active openclaw.service

. /etc/openclaw/openclaw.env
export NODE_OPTIONS NODE_EXTRA_CA_CERTS

node <<'NODE'
(async () => {
  try {
    const res = await fetch("https://example.com");
    console.log(JSON.stringify({fetchOk: res.ok, status: res.status, url: res.url}));
  } catch (err) {
    console.error("node_fetch_failed", err && (err.stack || err.message || String(err)));
    process.exit(1);
  }
})();
NODE

xvfb-run -a --server-args='-screen 0 1280x720x24' node <<'NODE'
const { chromium } = require('/usr/lib/node_modules/playwright');
(async () => {
  try {
    const browser = await chromium.launch({ headless: true, executablePath: "/usr/bin/google-chrome" });
    const page = await browser.newPage();
    await page.goto("https://example.com", { waitUntil: "domcontentloaded", timeout: 30000 });
    console.log(JSON.stringify({ title: await page.title(), url: page.url() }));
    await browser.close();
  } catch (err) {
    console.error("playwright_failed", err && (err.stack || err.message || String(err)));
    process.exit(1);
  }
})();
NODE

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
    if out and not out.endswith("\n"):
        sys.stdout.buffer.write(b"\n")
    if err.strip():
        sys.stderr.buffer.write(err.encode("utf-8", errors="replace"))
        if err and not err.endswith("\n"):
            sys.stderr.buffer.write(b"\n")
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
