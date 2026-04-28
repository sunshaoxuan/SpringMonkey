#!/usr/bin/env python3
import base64
import re
from pathlib import Path
import paramiko

def run(c, cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read() + e.read()).decode("utf-8", "replace")

def remote_patch_ensure_script(c) -> str:
    """宿主机 ensure 脚本：在 OpenClaw 升级后从 selection 改到 preemptive-compaction 包内做 proactive 校验。"""
    py = r'''
from pathlib import Path
p = Path("/usr/local/lib/openclaw/ensure_agent_society_runtime_guard.sh")
text = p.read_text(encoding="utf-8")
old = """selection_candidates = sorted(
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
    raise SystemExit(f"[agent-society-guard] preemptive compaction verification failed: missing {selection_missing}")"""
new = """selection_required = [
    "const proactiveThresholdTokens = Math.max(1, Math.floor(promptBudgetBeforeReserve * .9));",
    "const proactiveMessageThreshold = 48;",
]
check_text = None
compaction_candidates = sorted(
    [p for p in dist.glob("preemptive-compaction-*.js") if p.is_file()],
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if compaction_candidates:
    ct = compaction_candidates[0].read_text(encoding="utf-8")
    if all(item in ct for item in selection_required):
        check_text = ct
if check_text is None:
    selection_candidates = sorted(
        [p for p in dist.glob("selection-*.js") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not selection_candidates:
        raise SystemExit("[agent-society-guard] selection bundle not found after patch")
    check_text = selection_candidates[0].read_text(encoding="utf-8")
selection_missing = [item for item in selection_required if item not in check_text]
if selection_missing:
    raise SystemExit(f"[agent-society-guard] preemptive compaction verification failed: missing {selection_missing}")"""
if old not in text:
    raise SystemExit("old block not found in ensure script; edit manually")
p.write_text(text.replace(old, new, 1), encoding="utf-8")
print("patched_ensure_script")
'''
    b64 = base64.b64encode(py.encode("utf-8")).decode("ascii")
    return run(c, "echo " + b64 + " | base64 -d | python3", 30)

def main():
    ha = Path(r"c:/tmp/default/HOST_ACCESS.md")
    m = re.search(r"- Password:\s*`([^`]+)`", ha.read_text(encoding="utf-8"))
    pw = m.group(1)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("ccnode.briconbric.com", 8822, "root", pw, timeout=60)
    repo = "/var/lib/openclaw/repos/SpringMonkey"
    print(
        "git sync (hard reset to origin/main; fixes diverged host clone):\n",
        run(
            c,
            "cd "
            + repo
            + " && git fetch origin && git reset --hard origin/main 2>&1",
            90,
        )[:3000],
    )
    print("patch:\n", run(c, "cd " + repo + " && python3 scripts/openclaw/patch_preemptive_compaction_runtime_current.py 2>&1", 60))
    inrepo = repo + "/scripts/openclaw/ensure_agent_society_runtime_guard.sh"
    print("install ensure from repo (if present):\n", run(c, "test -f " + inrepo + " && install -m 755 " + inrepo + " /usr/local/lib/openclaw/ensure_agent_society_runtime_guard.sh && echo OK || echo NOFILE", 20))
    print("remote patch ensure (if old block still there):\n", remote_patch_ensure_script(c))
    print("guard:\n", run(c, "/usr/local/lib/openclaw/ensure_agent_society_runtime_guard.sh 2>&1", 120)[:5000])
    print("restart:\n", run(c, "systemctl restart openclaw.service; sleep 2; systemctl is-active openclaw.service; systemctl status openclaw.service --no-pager -l 2>&1 | head -18", 30))
    c.close()

if __name__ == "__main__":
    main()
