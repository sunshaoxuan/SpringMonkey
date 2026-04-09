#!/usr/bin/env python3
"""SSH 到汤猴宿主机，安装常驻浏览器的守护规则与清理定时器。"""
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

cat >/usr/local/lib/openclaw/browser_guard.py <<'PY'
#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import urllib.request

CDP = os.environ.get("OPENCLAW_BROWSER_CDP", "http://127.0.0.1:18800")
SENTINEL = os.environ.get("OPENCLAW_BROWSER_SENTINEL_URL", "about:blank")
MAX_TABS = int(os.environ.get("OPENCLAW_BROWSER_MAX_TABS", "3"))
HARD_TABS = int(os.environ.get("OPENCLAW_BROWSER_HARD_TABS", "6"))
MAX_RSS_KB = int(os.environ.get("OPENCLAW_BROWSER_MAX_RSS_KB", "1250000"))


def jget(url: str):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def raw(method: str, path: str, payload: dict | None = None):
    url = f"{CDP}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=8) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def get_chrome_rss_kb() -> int:
    try:
        out = subprocess.check_output(
            "ps -C chrome -o rss= 2>/dev/null; ps -C google-chrome -o rss= 2>/dev/null",
            shell=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return 0
    total = 0
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            total += int(line)
    return total


def ensure_sentinel(pages: list[dict]) -> None:
    if any((p.get("url") or "") == SENTINEL for p in pages):
        return
    raw("PUT", "/json/new?" + SENTINEL.replace(":", "%3A"))


def close_target(target_id: str) -> None:
    try:
        raw("GET", f"/json/close/{target_id}")
    except Exception:
        pass


def main() -> int:
    try:
        pages = jget(f"{CDP}/json/list")
    except Exception as exc:
        print(json.dumps({"ok": False, "reason": "cdp_unreachable", "detail": str(exc)}))
        return 0

    ensure_sentinel(pages)
    pages = jget(f"{CDP}/json/list")
    rss_kb = get_chrome_rss_kb()

    keep_ids: set[str] = set()
    sentinel = next((p for p in pages if (p.get("url") or "") == SENTINEL), None)
    if sentinel and sentinel.get("id"):
        keep_ids.add(sentinel["id"])

    # Keep the most recently listed non-sentinel page as the active working tab.
    non_sentinel = [p for p in pages if (p.get("url") or "") != SENTINEL]
    if non_sentinel and non_sentinel[-1].get("id"):
        keep_ids.add(non_sentinel[-1]["id"])

    should_trim = len(pages) > HARD_TABS or rss_kb > MAX_RSS_KB or len(pages) > MAX_TABS
    closed = []
    if should_trim:
        for page in pages:
            page_id = page.get("id")
            if not page_id or page_id in keep_ids:
                continue
            close_target(page_id)
            closed.append(page_id)

    pages_after = jget(f"{CDP}/json/list")
    print(json.dumps({
        "ok": True,
        "tabsBefore": len(pages),
        "tabsAfter": len(pages_after),
        "closed": closed,
        "rssKb": rss_kb,
        "sentinelUrl": SENTINEL,
        "maxTabs": MAX_TABS,
        "hardTabs": HARD_TABS,
        "maxRssKb": MAX_RSS_KB,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY

chmod 755 /usr/local/lib/openclaw/browser_guard.py

cat >/etc/systemd/system/openclaw-browser-guard.service <<'EOF'
[Unit]
Description=OpenClaw Browser Guard
After=network-online.target

[Service]
Type=oneshot
Environment=OPENCLAW_BROWSER_CDP=http://127.0.0.1:18800
Environment=OPENCLAW_BROWSER_SENTINEL_URL=about:blank
Environment=OPENCLAW_BROWSER_MAX_TABS=3
Environment=OPENCLAW_BROWSER_HARD_TABS=6
Environment=OPENCLAW_BROWSER_MAX_RSS_KB=1250000
ExecStart=/usr/bin/python3 /usr/local/lib/openclaw/browser_guard.py
User=root
EOF

cat >/etc/systemd/system/openclaw-browser-guard.timer <<'EOF'
[Unit]
Description=Run OpenClaw Browser Guard every 2 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=2min
Unit=openclaw-browser-guard.service

[Install]
WantedBy=timers.target
EOF

python3 <<'PY'
from pathlib import Path
p = Path("/var/lib/openclaw/.openclaw/workspace/TOOLS.md")
text = p.read_text(encoding="utf-8", errors="replace")
marker = "## Required Reasoning Rules\n"
insert = '''
## Browser Retention Rules

- The persistent browser service must keep exactly one sentinel tab at `about:blank`.
- Do not intentionally keep large numbers of tabs open between tasks.
- After browser-heavy work, prefer leaving only the active task tab plus the sentinel tab.
- Host guardrails will automatically trim excess tabs when tab count or memory crosses thresholds.

'''
if insert.strip() not in text:
    if marker in text:
        text = text.replace(marker, insert + marker, 1)
    else:
        text += "\n" + insert
    p.write_text(text, encoding="utf-8")
print(p)
PY

systemctl daemon-reload
systemctl enable --now openclaw-browser-guard.timer
systemctl start openclaw-browser-guard.service
sleep 2
systemctl is-active openclaw-browser-guard.timer
systemctl is-active openclaw-browser-guard.service || true
journalctl -u openclaw-browser-guard.service -n 20 --no-pager || true
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
