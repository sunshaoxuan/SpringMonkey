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

old_lifecycle = '''\tconst typingSignals = createTypingSignaler({\n\t\ttyping,\n\t\tmode: typingMode,\n\t\tisHeartbeat\n\t});\n'''
new_lifecycle = '''\tconst typingSignals = createTypingSignaler({\n\t\ttyping,\n\t\tmode: typingMode,\n\t\tisHeartbeat\n\t});\n\tconst shouldForceVisibleLifecycle = !isHeartbeat && sessionCtx.ChatType === "direct" && typeof opts?.onBlockReply === "function";\n\t\tlet lifecycleAckSent = false;\n\t\tlet lifecycleProgressSent = false;\n\t\tlet lifecycleAckTimer = null;\n\t\tlet lifecycleProgressTimer = null;\n\t\tconst clearLifecycleTimers = () => {\n\t\t\tif (lifecycleAckTimer) {\n\t\t\t\tclearTimeout(lifecycleAckTimer);\n\t\t\t\tlifecycleAckTimer = null;\n\t\t\t}\n\t\t\tif (lifecycleProgressTimer) {\n\t\t\t\tclearTimeout(lifecycleProgressTimer);\n\t\t\t\tlifecycleProgressTimer = null;\n\t\t\t}\n\t\t};\n\t\tconst sendLifecyclePayload = async (text) => {\n\t\t\tif (!shouldForceVisibleLifecycle || !text || !text.trim()) return false;\n\t\t\ttry {\n\t\t\t\tawait opts.onBlockReply({ text });\n\t\t\t\treturn true;\n\t\t\t} catch (err) {\n\t\t\t\tlogVerbose(`lifecycle notice delivery failed: ${String(err)}`);\n\t\t\t\treturn false;\n\t\t\t}\n\t\t};\n\t\tconst scheduleLifecycleNotices = () => {\n\t\t\tif (!shouldForceVisibleLifecycle) return;\n\t\t\tif (!lifecycleAckTimer) {\n\t\t\t\tlifecycleAckTimer = setTimeout(() => {\n\t\t\t\t\tif (lifecycleAckSent) return;\n\t\t\t\t\tlifecycleAckSent = true;\n\t\t\t\t\tvoid sendLifecyclePayload("收到，我已经开始处理这项请求。接下来我会先确认状态，再执行必要操作，完成后向你汇报结果。");\n\t\t\t\t}, 2500);\n\t\t\t\tlifecycleAckTimer.unref?.();\n\t\t\t}\n\t\t\tif (!lifecycleProgressTimer) {\n\t\t\t\tlifecycleProgressTimer = setTimeout(() => {\n\t\t\t\t\tif (lifecycleProgressSent) return;\n\t\t\t\t\tlifecycleProgressSent = true;\n\t\t\t\t\tvoid sendLifecyclePayload("进度更新：我还在处理中。当前正在执行中间步骤，完成后会把我做了什么和当前状态一起汇报给你。");\n\t\t\t\t}, 20000);\n\t\t\t\tlifecycleProgressTimer.unref?.();\n\t\t\t}\n\t\t};\n\t\tconst buildVisibleReplyFallbackPayload = () => shouldForceVisibleLifecycle ? {\n\t\t\ttext: "这轮任务已经执行结束，但没有正常生成最终汇报。我会重新整理当前状态并尽快补发说明。"\n\t\t} : void 0;\n'''

old_signal_run_start = '''\t\tawait typingSignals.signalRunStart();\n'''
new_signal_run_start = '''\t\tawait typingSignals.signalRunStart();\n\t\tscheduleLifecycleNotices();\n'''

old_empty_payloads = '''\t\tif (payloadArray.length === 0) return finalizeWithFollowup(void 0, queueKey, runFollowupTurn);\n'''
new_empty_payloads = '''\t\tif (payloadArray.length === 0) {\n\t\t\tclearLifecycleTimers();\n\t\t\treturn finalizeWithFollowup(buildVisibleReplyFallbackPayload(), queueKey, runFollowupTurn);\n\t\t}\n'''

old_empty_reply_payloads = '''\t\tif (replyPayloads.length === 0) return finalizeWithFollowup(void 0, queueKey, runFollowupTurn);\n'''
new_empty_reply_payloads = '''\t\tif (replyPayloads.length === 0) {\n\t\t\tclearLifecycleTimers();\n\t\t\treturn finalizeWithFollowup(buildVisibleReplyFallbackPayload(), queueKey, runFollowupTurn);\n\t\t}\n'''

old_final_return = '''\t\tif (responseUsageLine) finalPayloads = appendUsageLine(finalPayloads, responseUsageLine);\n\t\treturn finalizeWithFollowup(finalPayloads.length === 1 ? finalPayloads[0] : finalPayloads, queueKey, runFollowupTurn);\n'''
new_final_return = '''\t\tif (responseUsageLine) finalPayloads = appendUsageLine(finalPayloads, responseUsageLine);\n\t\tclearLifecycleTimers();\n\t\treturn finalizeWithFollowup(finalPayloads.length === 1 ? finalPayloads[0] : finalPayloads, queueKey, runFollowupTurn);\n'''

old_finally = '''\t} finally {\n\t\treplyOperation.complete();\n\t\tblockReplyPipeline?.stop();\n\t\ttyping.markRunComplete();\n\t\ttyping.markDispatchIdle();\n\t}\n'''
new_finally = '''\t} finally {\n\t\tclearLifecycleTimers();\n\t\treplyOperation.complete();\n\t\tblockReplyPipeline?.stop();\n\t\ttyping.markRunComplete();\n\t\ttyping.markDispatchIdle();\n\t}\n'''

if "shouldForceVisibleLifecycle" not in text:
    if old_lifecycle not in text:
        raise SystemExit("lifecycle insertion anchor not found")
    text = text.replace(old_lifecycle, new_lifecycle, 1)

if "scheduleLifecycleNotices();" not in text:
    if old_signal_run_start not in text:
        raise SystemExit("signalRunStart anchor not found")
    text = text.replace(old_signal_run_start, new_signal_run_start, 1)

if "buildVisibleReplyFallbackPayload()" not in text:
    if old_empty_payloads not in text:
        raise SystemExit("empty payload anchor not found")
    text = text.replace(old_empty_payloads, new_empty_payloads, 1)
    if old_empty_reply_payloads not in text:
        raise SystemExit("empty reply payload anchor not found")
    text = text.replace(old_empty_reply_payloads, new_empty_reply_payloads, 1)

if "clearLifecycleTimers();\n\t\treturn finalizeWithFollowup(finalPayloads.length === 1 ? finalPayloads[0] : finalPayloads, queueKey, runFollowupTurn);" not in text:
    if old_final_return not in text:
        raise SystemExit("final return anchor not found")
    text = text.replace(old_final_return, new_final_return, 1)

if "clearLifecycleTimers();\n\t\treplyOperation.complete();" not in text:
    if old_finally not in text:
        raise SystemExit("finally anchor not found")
    text = text.replace(old_finally, new_finally, 1)

backup = target.with_name(f"{target.name}.bak-three-phase-reply-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
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
    "lifecycle_guard": "shouldForceVisibleLifecycle" in text,
    "ack_notice": "收到，我已经开始处理这项请求" in text,
    "progress_notice": "进度更新：我还在处理中" in text,
    "fallback_payload": "buildVisibleReplyFallbackPayload" in text,
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
