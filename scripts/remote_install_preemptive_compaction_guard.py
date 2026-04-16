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
import json
import shutil

cfg_path = Path("/var/lib/openclaw/.openclaw/openclaw.json")
cfg_backup = cfg_path.with_name(f"openclaw.json.bak-compaction-guard-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
shutil.copy2(cfg_path, cfg_backup)
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
comp = cfg.setdefault("agents", {}).setdefault("defaults", {}).setdefault("compaction", {})
comp["mode"] = "safeguard"
comp["reserveTokens"] = 42000
comp["keepRecentTokens"] = 8000
comp["reserveTokensFloor"] = 32000
comp["recentTurnsPreserve"] = 6
cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"CONFIG_BACKUP {cfg_backup}")

dist = Path("/usr/lib/node_modules/openclaw/dist")
candidates = sorted(dist.glob("pi-embedded-*.js"), key=lambda p: p.stat().st_mtime, reverse=True)
if not candidates:
    raise SystemExit("pi-embedded bundle not found")
target = candidates[0]
text = target.read_text(encoding="utf-8")
old = '''function shouldPreemptivelyCompactBeforePrompt(params) {\n\tconst estimatedPromptTokens = estimatePrePromptTokens(params);\n\tconst promptBudgetBeforeReserve = Math.max(1, Math.floor(params.contextTokenBudget) - Math.max(0, Math.floor(params.reserveTokens)));\n\tconst overflowTokens = Math.max(0, estimatedPromptTokens - promptBudgetBeforeReserve);\n\tconst toolResultPotential = estimateToolResultReductionPotential({\n\t\tmessages: params.messages,\n\t\tcontextWindowTokens: params.contextTokenBudget\n\t});\n\tconst overflowChars = overflowTokens * ESTIMATED_CHARS_PER_TOKEN;\n\tconst truncationBufferChars = TRUNCATION_ROUTE_BUFFER_TOKENS * ESTIMATED_CHARS_PER_TOKEN;\n\tconst truncateOnlyThresholdChars = Math.max(overflowChars + truncationBufferChars, Math.ceil(overflowChars * 1.5));\n\tconst toolResultReducibleChars = toolResultPotential.maxReducibleChars;\n\tlet route = "fits";\n\tif (overflowTokens > 0) if (toolResultReducibleChars <= 0) route = "compact_only";\n\telse if (toolResultReducibleChars >= truncateOnlyThresholdChars) route = "truncate_tool_results_only";\n\telse route = "compact_then_truncate";\n\treturn {\n\t\troute,\n\t\tshouldCompact: route === "compact_only" || route === "compact_then_truncate",\n\t\testimatedPromptTokens,\n\t\tpromptBudgetBeforeReserve,\n\t\toverflowTokens,\n\t\ttoolResultReducibleChars\n\t};\n}\n'''
new = '''function shouldPreemptivelyCompactBeforePrompt(params) {\n\tconst estimatedPromptTokens = estimatePrePromptTokens(params);\n\tconst promptBudgetBeforeReserve = Math.max(1, Math.floor(params.contextTokenBudget) - Math.max(0, Math.floor(params.reserveTokens)));\n\tconst overflowTokens = Math.max(0, estimatedPromptTokens - promptBudgetBeforeReserve);\n\tconst toolResultPotential = estimateToolResultReductionPotential({\n\t\tmessages: params.messages,\n\t\tcontextWindowTokens: params.contextTokenBudget\n\t});\n\tconst overflowChars = overflowTokens * ESTIMATED_CHARS_PER_TOKEN;\n\tconst truncationBufferChars = TRUNCATION_ROUTE_BUFFER_TOKENS * ESTIMATED_CHARS_PER_TOKEN;\n\tconst truncateOnlyThresholdChars = Math.max(overflowChars + truncationBufferChars, Math.ceil(overflowChars * 1.5));\n\tconst toolResultReducibleChars = toolResultPotential.maxReducibleChars;\n\tconst proactiveThresholdTokens = Math.max(1, Math.floor(promptBudgetBeforeReserve * .82));\n\tconst proactiveMessageThreshold = 48;\n\tlet route = "fits";\n\tif (overflowTokens > 0) if (toolResultReducibleChars <= 0) route = "compact_only";\n\telse if (toolResultReducibleChars >= truncateOnlyThresholdChars) route = "truncate_tool_results_only";\n\telse route = "compact_then_truncate";\n\telse if (params.messages.length >= proactiveMessageThreshold && estimatedPromptTokens >= proactiveThresholdTokens) route = "compact_only";\n\treturn {\n\t\troute,\n\t\tshouldCompact: route === "compact_only" || route === "compact_then_truncate",\n\t\testimatedPromptTokens,\n\t\tpromptBudgetBeforeReserve,\n\t\toverflowTokens,\n\t\ttoolResultReducibleChars\n\t};\n}\n'''
if new not in text:
    if old not in text:
        raise SystemExit("preemptive compaction function anchor not found")
    backup = target.with_name(f"{target.name}.bak-preemptive-compaction-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(target, backup)
    text = text.replace(old, new, 1)
    target.write_text(text, encoding="utf-8")
    print(f"BUNDLE_BACKUP {backup}")
print(f"PATCHED_BUNDLE {target}")
PY

systemctl restart openclaw.service
sleep 12
systemctl is-active openclaw.service
curl -fsS http://127.0.0.1:18789/healthz >/dev/null
curl -fsS http://127.0.0.1:18789/line/webhook >/dev/null
python3 <<'PY'
import json
from pathlib import Path
cfg = json.loads(Path("/var/lib/openclaw/.openclaw/openclaw.json").read_text(encoding="utf-8"))
print(json.dumps(cfg["agents"]["defaults"]["compaction"], ensure_ascii=False, indent=2))
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
