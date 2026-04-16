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
import shutil
from datetime import datetime
import json

dist = Path("/usr/lib/node_modules/openclaw/dist")
candidates = sorted(dist.glob("pi-embedded-*.js"), key=lambda p: p.stat().st_mtime, reverse=True)
if not candidates:
    raise SystemExit("pi-embedded bundle not found")
target = candidates[0]
text = target.read_text(encoding="utf-8")

var_old = 'let timeoutCompactionAttempts = 0;\n'
var_new = '''let timeoutCompactionAttempts = 0;\n\t\t\tlet sameModelTimeoutRetryCount = 0;\n\t\t\tlet sameModelTimeoutRetryKey = null;\n\t\t\tconst MAX_OLLAMA_QWEN_TIMEOUT_RETRIES = 2;\n'''

block_old = '''\t\t\t\t\tif (timedOut && !timedOutDuringCompaction) {\n\t\t\t\t\t\tconst lastTurnPromptTokens = derivePromptTokens(lastRunPromptUsage);\n\t\t\t\t\t\tconst tokenUsedRatio = lastTurnPromptTokens != null && ctxInfo.tokens > 0 ? lastTurnPromptTokens / ctxInfo.tokens : 0;\n\t\t\t\t\t\tif (timeoutCompactionAttempts >= MAX_TIMEOUT_COMPACTION_ATTEMPTS) log$16.warn(`[timeout-compaction] already attempted timeout compaction ${timeoutCompactionAttempts} time(s); falling through to failover rotation`);\n\t\t\t\t\t\telse if (tokenUsedRatio > .65) {\n'''

block_new = '''\t\t\t\t\tif (timedOut && !timedOutDuringCompaction) {\n\t\t\t\t\t\tconst currentTimeoutRetryKey = `${provider}/${modelId}`;\n\t\t\t\t\t\tif (sameModelTimeoutRetryKey !== currentTimeoutRetryKey) {\n\t\t\t\t\t\t\tsameModelTimeoutRetryKey = currentTimeoutRetryKey;\n\t\t\t\t\t\t\tsameModelTimeoutRetryCount = 0;\n\t\t\t\t\t\t}\n\t\t\t\t\t\tconst lastTurnPromptTokens = derivePromptTokens(lastRunPromptUsage);\n\t\t\t\t\t\tconst tokenUsedRatio = lastTurnPromptTokens != null && ctxInfo.tokens > 0 ? lastTurnPromptTokens / ctxInfo.tokens : 0;\n\t\t\t\t\t\tif (timeoutCompactionAttempts >= MAX_TIMEOUT_COMPACTION_ATTEMPTS) log$16.warn(`[timeout-compaction] already attempted timeout compaction ${timeoutCompactionAttempts} time(s); falling through to failover rotation`);\n\t\t\t\t\t\telse if (tokenUsedRatio > .65) {\n'''

retry_anchor_old = '''\t\t\t\t\t\t\t} else log$16.warn(`[timeout-compaction] compaction did not reduce context for ${provider}/${modelId}; falling through to normal handling`);\n\t\t\t\t\t\t}\n\t\t\t\t\t}\n\t\t\t\t\tconst contextOverflowError = !aborted ? (() => {\n'''

retry_anchor_new = '''\t\t\t\t\t\t\t} else log$16.warn(`[timeout-compaction] compaction did not reduce context for ${provider}/${modelId}; falling through to normal handling`);\n\t\t\t\t\t\t}\n\t\t\t\t\t\tif (!aborted && provider === "ollama" && modelId === "qwen3:14b" && sameModelTimeoutRetryCount < MAX_OLLAMA_QWEN_TIMEOUT_RETRIES) {\n\t\t\t\t\t\t\tsameModelTimeoutRetryCount += 1;\n\t\t\t\t\t\t\tlastRetryFailoverReason = mergeRetryFailoverReason({\n\t\t\t\t\t\t\t\tprevious: lastRetryFailoverReason,\n\t\t\t\t\t\t\t\tfailoverReason: "timeout",\n\t\t\t\t\t\t\t\ttimedOut: true\n\t\t\t\t\t\t\t});\n\t\t\t\t\t\t\tlog$16.warn(`[model-timeout-retry] retrying ${provider}/${modelId} after timeout (${sameModelTimeoutRetryCount + 1}/3 total attempts) before fallback`);\n\t\t\t\t\t\t\tcontinue;\n\t\t\t\t\t\t}\n\t\t\t\t\t\tif (!aborted && provider === "ollama" && modelId === "qwen3:14b" && sameModelTimeoutRetryCount >= MAX_OLLAMA_QWEN_TIMEOUT_RETRIES) log$16.warn(`[model-timeout-retry] exhausted qwen timeout retries for ${provider}/${modelId}; allowing fallback`);\n\t\t\t\t\t}\n\t\t\t\t\tconst contextOverflowError = !aborted ? (() => {\n'''

if "MAX_OLLAMA_QWEN_TIMEOUT_RETRIES" not in text:
    if var_old not in text:
        raise SystemExit("timeout variable anchor not found")
    text = text.replace(var_old, var_new, 1)

if "currentTimeoutRetryKey" not in text:
    if block_old not in text:
        raise SystemExit("timeout block anchor not found")
    text = text.replace(block_old, block_new, 1)

if "[model-timeout-retry]" not in text:
    if retry_anchor_old not in text:
        raise SystemExit("timeout retry insertion anchor not found")
    text = text.replace(retry_anchor_old, retry_anchor_new, 1)

backup = target.with_name(f"{target.name}.bak-qwen-timeout-retry-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
shutil.copy2(target, backup)
target.write_text(text, encoding="utf-8")
print(f"PATCHED_BUNDLE {target}")
print(f"BACKUP_BUNDLE {backup}")

cfg = Path("/var/lib/openclaw/.openclaw/openclaw.json")
cfg_data = json.loads(cfg.read_text(encoding="utf-8"))
jobs_path = Path("/var/lib/openclaw/.openclaw/cron/jobs.json")
jobs_data = json.loads(jobs_path.read_text(encoding="utf-8"))
updated = []
for job in jobs_data.get("jobs", []):
    payload = job.setdefault("payload", {})
    if payload.get("model") == "ollama/qwen3:14b":
        timeout = int(payload.get("timeoutSeconds", 0) or 0)
        if timeout < 1800:
            payload["timeoutSeconds"] = 1800
            updated.append(job.get("name") or job.get("id"))
jobs_path.write_text(json.dumps(jobs_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("UPDATED_QWEN_TIMEOUT_JOBS", json.dumps(updated, ensure_ascii=False))
PY

systemctl restart openclaw.service
sleep 8
systemctl is-active openclaw.service
curl -fsS http://127.0.0.1:18789/healthz >/dev/null
python3 <<'PY'
import json
from pathlib import Path
jobs = json.loads(Path("/var/lib/openclaw/.openclaw/cron/jobs.json").read_text(encoding="utf-8"))["jobs"]
rows = []
for job in jobs:
    payload = job.get("payload", {})
    if payload.get("model") == "ollama/qwen3:14b":
        rows.append({
            "name": job.get("name"),
            "timeoutSeconds": payload.get("timeoutSeconds"),
            "thinking": payload.get("thinking"),
            "delivery": job.get("delivery", {}).get("channel"),
        })
print(json.dumps(rows, ensure_ascii=False, indent=2))
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
