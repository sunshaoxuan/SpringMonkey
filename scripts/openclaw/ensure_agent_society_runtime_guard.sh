#!/usr/bin/env bash
set -euo pipefail
export HOME=/var/lib/openclaw
REPO=/var/lib/openclaw/repos/SpringMonkey
PATCH="${REPO}/scripts/openclaw/patch_agent_society_runtime_current.py"
PREEMPTIVE_PATCH="${REPO}/scripts/openclaw/patch_preemptive_compaction_runtime_current.py"
KERNEL="${REPO}/scripts/openclaw/agent_society_kernel.py"
RUNTIME_GAP="${REPO}/scripts/openclaw/agent_society_runtime_record_gap.py"
if [ ! -f "$PATCH" ]; then
  echo "[agent-society-guard] missing patch script: $PATCH" >&2
  exit 1
fi
if [ ! -f "$PREEMPTIVE_PATCH" ]; then
  echo "[agent-society-guard] missing patch script: $PREEMPTIVE_PATCH" >&2
  exit 1
fi
if [ ! -f "$KERNEL" ]; then
  echo "[agent-society-guard] missing kernel script: $KERNEL" >&2
  exit 1
fi
if [ ! -f "$RUNTIME_GAP" ]; then
  echo "[agent-society-guard] missing runtime gap script: $RUNTIME_GAP" >&2
  exit 1
fi
python3 "$PATCH" >/tmp/agent-society-runtime-guard.log 2>&1 || {
  cat /tmp/agent-society-runtime-guard.log >&2 || true
  exit 1
}
python3 "$PREEMPTIVE_PATCH" >/tmp/preemptive-compaction-runtime-guard.log 2>&1 || {
  cat /tmp/preemptive-compaction-runtime-guard.log >&2 || true
  exit 1
}
install -d -m 755 /var/lib/openclaw/.openclaw/workspace/agent_society_kernel/sessions
python3 "$KERNEL" --root /var/lib/openclaw/.openclaw/workspace/agent_society_kernel new-session --channel system --user-id bootstrap --prompt "refresh agent society kernel state root before gateway start" >/tmp/agent-society-kernel-bootstrap.log 2>&1 || {
  cat /tmp/agent-society-kernel-bootstrap.log >&2 || true
  exit 1
}
python3 - <<'PY'
from pathlib import Path
dist = Path("/usr/lib/node_modules/openclaw/dist")
candidates = sorted(
    [
        p
        for p in dist.glob("agent-runner.runtime-*.js")
        if p.name != "agent-runner.runtime.js" and p.is_file()
    ],
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if not candidates:
    raise SystemExit("[agent-society-guard] runtime bundle not found after patch")
text = candidates[0].read_text(encoding="utf-8")
required = [
    "[runtime-goal-intent-task-agent-society-protocol]",
    "shouldApplyAgentSocietyProtocol",
    "extract all relevant intents",
    "create or refine a helper tool",
    "[runtime-self-improvement-toolsmith-protocol]",
    "classify the failure into a capability gap",
    "[runtime-kernel-session]",
    "ensure-session",
]
missing = [item for item in required if item not in text]
if missing:
    raise SystemExit(f"[agent-society-guard] patched bundle verification failed: missing {missing}")
workspace = Path("/var/lib/openclaw/.openclaw/workspace/AGENT_SOCIETY_RUNTIME.md")
if not workspace.exists():
    raise SystemExit("[agent-society-guard] workspace bridge file missing")
selection_candidates = sorted(
    [p for p in dist.glob("selection-*.js") if p.is_file()],
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if not selection_candidates:
    raise SystemExit("[agent-society-guard] selection bundle not found after patch")
selection_text = selection_candidates[0].read_text(encoding="utf-8")
selection_required = [
    "const proactiveThresholdTokens = Math.max(1, Math.floor(promptBudgetBeforeReserve * .9));",
    "const proactiveMessageThreshold = 48;",
]
selection_missing = [item for item in selection_required if item not in selection_text]
if selection_missing:
    raise SystemExit(f"[agent-society-guard] preemptive compaction verification failed: missing {selection_missing}")
kernel_workspace = Path("/var/lib/openclaw/.openclaw/workspace/AGENT_SOCIETY_KERNEL.md")
kernel_state_root = Path("/var/lib/openclaw/.openclaw/workspace/agent_society_kernel")
if not kernel_workspace.exists():
    raise SystemExit("[agent-society-guard] kernel workspace file missing")
if not (kernel_state_root / "sessions").exists():
    raise SystemExit("[agent-society-guard] kernel state root missing")
print("[agent-society-guard] patch verification ok")
PY
