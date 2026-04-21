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

REMOTE = r"""
set -euo pipefail

python3 <<'PY'
from pathlib import Path
from datetime import datetime
import shutil

dist = Path("/usr/lib/node_modules/openclaw/dist")
target = dist / "agent-runner.runtime-CTlghBhJ.js"
if not target.exists():
    raise SystemExit("agent-runner runtime bundle not found")

text = target.read_text(encoding="utf-8")

old_anchor = '''\tconst shouldEmitToolResult = createShouldEmitToolResult({\n\t\tsessionKey,\n\t\tstorePath,\n\t\tresolvedVerboseLevel\n\t});\n'''
new_anchor = '''\tconst shouldApplyOperationalExecutionProtocol = (() => {\n\t\tif (isHeartbeat || sessionCtx.ChatType !== "direct") return false;\n\t\tconst promptText = typeof followupRun.prompt === "string" ? followupRun.prompt : "";\n\t\tif (!promptText.trim()) return false;\n\t\tconst hasOperationVerb = /登录|登入|log\\s?in|sign\\s?in|change\\s+password|reset\\s+password|修改密码|重置密码|打开|访问|进入|navigate|open|visit|click|点击|search|查找|设置|配置|保存密码|提交|上传|download|upload|修复|排查|测试/u.test(promptText);\n\t\tconst hasOperationTarget = /邮箱|email|mail|账号|account|网站|网页|browser|登录页|设置页|password|密码|google|docs|小红书|line|discord|slack|notion|service|系统|portal|dashboard/u.test(promptText);\n\t\treturn hasOperationVerb && hasOperationTarget;\n\t})();\n\tconst OPERATIONAL_EXECUTION_PROTOCOL = `[runtime-operational-execution-protocol]\\nThis is an operational task. Do not rely on one long thinking pass and do not stop at analysis.\\nUse a plan-execute-observe-replan loop:\\n1. identify the concrete goal and likely target system\\n2. break the task into ordered executable steps\\n3. choose the right tool for the current step\\n4. execute exactly one step\\n5. inspect the result before deciding the next step\\n6. continue until completed or a concrete blocker is proven\\nTool selection rules:\\n- For website or account tasks, prefer browser-first execution.\\n- If the login URL or system is unknown, use browser or web discovery first to identify it.\\n- Use exec/read only for local files, host config, or command-line verification.\\n- Do not claim a password was changed, saved, or verified unless the observed result proves it.\\n- If credentials, 2FA, captcha, permissions, or confirmation are missing, report the exact blocker instead of pretending completion.\\nFinal response rules:\\n- Report what you actually did.\\n- Report the current state.\\n- Report any remaining blocker or next step if unfinished.`;\n\tif (shouldApplyOperationalExecutionProtocol && typeof followupRun.prompt === "string" && !followupRun.prompt.includes("[runtime-operational-execution-protocol]")) followupRun.prompt = `${OPERATIONAL_EXECUTION_PROTOCOL}\\n\\nUser task:\\n${followupRun.prompt}`;\n\tconst shouldEmitToolResult = createShouldEmitToolResult({\n\t\tsessionKey,\n\t\tstorePath,\n\t\tresolvedVerboseLevel\n\t});\n'''

if "[runtime-operational-execution-protocol]" not in text:
    if old_anchor not in text:
        raise SystemExit("operational protocol anchor not found")
    text = text.replace(old_anchor, new_anchor, 1)

backup = target.with_name(f"{target.name}.bak-operational-execution-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
shutil.copy2(target, backup)
target.write_text(text, encoding="utf-8")
print(f"PATCHED_BUNDLE {target}")
print(f"BACKUP_BUNDLE {backup}")
PY

systemctl restart openclaw.service
sleep 15
systemctl is-active openclaw.service
curl -fsS http://127.0.0.1:18789/healthz >/dev/null
python3 <<'PY'
from pathlib import Path
text = Path("/usr/lib/node_modules/openclaw/dist/agent-runner.runtime-CTlghBhJ.js").read_text(encoding="utf-8")
checks = {
    "operational_protocol_token": "[runtime-operational-execution-protocol]" in text,
    "operational_guard": "shouldApplyOperationalExecutionProtocol" in text,
    "browser_first_rule": "prefer browser-first execution" in text,
}
print(checks)
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
    _, stdout, stderr = client.exec_command(REMOTE.strip(), get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    return 0 if "active" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
