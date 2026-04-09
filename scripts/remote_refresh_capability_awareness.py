#!/usr/bin/env python3
"""SSH 到汤猴宿主机，刷新 workspace 注入文件中的能力认知基线。"""
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

python3 <<'PY'
from pathlib import Path

workspace = Path("/var/lib/openclaw/.openclaw/workspace")
tools_path = workspace / "TOOLS.md"

content = '''# TOOLS.md - Runtime Capability Baseline

This file tells the runtime agent what is actually available on this host right now.

## Current Runtime Capability Baseline

- Web search is available.
  Provider: Brave search via the shared gateway environment.
- Web fetch is available.
  Node HTTPS is configured to use the system CA store.
- Browser automation is enabled.
  Google Chrome is installed at `/usr/bin/google-chrome`.
  Browser backend support is present on the host and may be used when visual navigation is needed.
- Playwright is installed on the host.
- Exec and process tools are available from both Discord and LINE.

## Service Safety Rules

- Do not kill the OpenClaw gateway process by PID during routine cleanup or diagnosis.
- Do not use `kill`, `pkill`, or `killall` against `openclaw`, `openclaw-gateway`, `node ... openclaw`, or `openclaw.service` unless the user explicitly asks for destructive process termination.
- If OpenClaw needs a restart, prefer `systemctl restart openclaw.service`.
- When checking dead or stuck scheduled tasks, inspect cron/job state first. Do not treat the gateway process itself as a dead task.
- Cron jobs with `delivery.channel = line` must keep delivering to LINE unless the user explicitly authorizes a different delivery target.

## Browser Retention Rules

- The persistent browser service must keep exactly one sentinel tab at `about:blank`.
- Do not intentionally keep large numbers of tabs open between tasks.
- After browser-heavy work, prefer leaving only the active task tab plus the sentinel tab.
- Host guardrails will automatically trim excess tabs when tab count or memory crosses thresholds.

## Required Reasoning Rules

- Do not claim that you lack internet access unless the current turn actually proves that the available web tools cannot be used.
- If `web_search`, `web_fetch`, or `browser` fails in the current turn, describe it as a current execution failure, not as a permanent lack of capability.
- Prefer `web_search` and `web_fetch` for ordinary page retrieval.
- Use `browser` when a page needs visual interaction, JavaScript rendering, login state, or click/navigation behavior.
- If browser backend is temporarily unavailable, say: `本轮 browser backend 不可用` or `本轮网页访问失败`, not `我没有上网能力`.
'''

tools_path.write_text(content, encoding="utf-8")
print(tools_path)
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
