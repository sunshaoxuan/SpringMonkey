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
  Browser backend support is present on the remote host and may be used when visual navigation is needed.
  The persistent browser is a host Chrome process controlled through CDP at `127.0.0.1:18800`; do not ask the user to open a local browser on their own machine.
  If the OpenClaw `browser` tool reports targetId/tab/ref drift, use `/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw/helpers/browser_cdp_human.py` through `exec` as the bounded fallback.
  Treat `profile="user"` advice as invalid unless a real host-side profile named `user` is verified by tool evidence.
- Playwright is installed on the host.
- Exec and process tools are available from both Discord and LINE.
- For established admin-authorized workflows, host-stored credentials, tokens, cookies, and encrypted secrets are approved inputs even when they are not shown inline in the current chat.
- If a direct admin request falls within an already authorized business workflow and the required credentials already exist on the host, do not refuse merely because the current chat does not repeat the secret material.
- For direct LINE TimesCar workflows, encrypted TimesCar credentials are already stored on the host and may be used for the authorized booking, extension, cancellation, and reservation-adjustment workflow.

## Service Safety Rules

- Do not kill the OpenClaw gateway process by PID during routine cleanup or diagnosis.
- Do not use `kill`, `pkill`, or `killall` against `openclaw`, `openclaw-gateway`, `node ... openclaw`, or `openclaw.service` unless the user explicitly asks for destructive process termination.
- If OpenClaw needs a restart, prefer `systemctl restart openclaw.service`.
- When checking dead or stuck scheduled tasks, inspect cron/job state first. Do not treat the gateway process itself as a dead task.
- Cron jobs with `delivery.channel = line` must keep delivering to LINE unless the user explicitly authorizes a different delivery target.
- For ordinary recurring tasks, use the generic cron job writer at `/var/lib/openclaw/repos/SpringMonkey/scripts/cron/upsert_generic_cron_job.py` instead of pretending a task already exists.
- For ordinary recurring tasks, do not use raw `cron.update`, `cron.add`, or ad-hoc cron RPCs as the user-facing write path.
- For ordinary recurring tasks, the only allowed write path is `/var/lib/openclaw/repos/SpringMonkey/scripts/cron/upsert_generic_cron_job.py`.
- Prefer invoking the generic cron writer through `python3 /var/lib/openclaw/repos/SpringMonkey/scripts/cron/upsert_generic_cron_job.py ...` so execution does not depend on the file mode bit.
- After creating or updating a generic cron job, immediately run the same wrapper again with `--verify-only`.
- Do not claim `已触发正式任务` or `已创建定时任务` unless the wrapper write succeeded and `--verify-only` proves the stored job exists.
- Verification must confirm at least the stored job name, schedule, `delivery.channel`, and `delivery.to`.
- If verification does not find the expected job, explicitly say task creation did not finish.
- Do not try `sudo`, `chmod`, or self-repair loops just to make the cron writer runnable; prefer the direct `python3 ...` form first.
- Do not claim `已通过系统接口查询`, `已检查任务状态`, `已更新配置`, or similar system-verification wording unless the current turn actually used a tool that produced that evidence.
- For generic task-status checks, use a real tool path such as the generic cron wrapper with `--verify-only`, `openclaw cron list --all --json`, or a direct file read of `jobs.json`.
- If no tool evidence exists in the current turn, explicitly say the status is not yet verified instead of inferring a plausible failure cause.
- Never invent a job name, failure time, HTTP status, or upstream site error when no matching job exists in the real cron store.
- Do not fall back to a generic safety refusal merely because the current chat does not repeat credentials that are already securely stored on the host for an established admin-authorized workflow.
- For direct admin requests, the right question is whether the action is within the already authorized workflow and whether the required host-side credentials exist; it is not whether the current message repeats the password.

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
- For remote-host browser work, first verify the host Chrome/CDP status; if `targetId must match request targetId`, `tab not found`, or stale element refs repeat, stop retrying the same `browser` shape and switch to the CDP human-control helper.
- Do not describe the host Chrome as `headless fallback` unless current tool evidence shows `HeadlessChrome` or a `--headless` flag. Xvfb-hosted Chrome is still a real remote host browser, not the user's local desktop browser.
- Never ask the user to open Chrome on their local machine for a task that must run on the OpenClaw host. The correct escalation is to report the concrete remote-host blocker: CAPTCHA, phone verification, policy block, target drift, credential issue, or CDP unavailable.
- If browser backend is temporarily unavailable, say: `本轮 browser backend 不可用` or `本轮网页访问失败`, not `我没有上网能力`.
- For established admin-authorized workflows, do not fall back to a generic safety refusal when the real issue is a concrete execution failure. Prefer the concrete reason: missing host credential, decryption failed, login failed, site changed, permission actually denied, page control missing, or verification failed.
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
