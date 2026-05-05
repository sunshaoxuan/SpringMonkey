#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]

BEHAVIOR_PREFIXES = (
    "config/",
    "docs/policies/",
    "docs/ops/",
    "docs/runtime-notes/",
    "scripts/cron/",
    "scripts/deploy/",
    "scripts/news/",
    "scripts/openclaw/",
    "scripts/patch/",
)

BEHAVIOR_EXACT = {
    "config/openclaw/intent_tools.json",
    "config/openclaw/harness.json",
    "config/openclaw/skills.json",
    "scripts/INDEX.md",
    "docs/CAPABILITY_INDEX.md",
    "docs/registry/GATEWAY.md",
    "docs/registry/tools_and_skills_manifest.json",
    "scripts/remote_install_direct_discord_cron.py",
    "scripts/remote_refresh_capability_awareness.py",
    "scripts/remote_install_repo_sync_timer.py",
    "scripts/openclaw_behavior_rule_gate.py",
    "scripts/test_openclaw_behavior_rule_gate.py",
    "scripts/test_repository_guardrails.py",
    "scripts/openclaw/intent_tool_router.py",
    "scripts/openclaw/verify_intent_tool_registry.py",
    "scripts/openclaw/verify_harness_registry.py",
    "scripts/openclaw/test_intent_tool_router.py",
    "scripts/openclaw/test_intent_tool_registry.py",
}

BEHAVIOR_REMOTE_INSTALL_PREFIX = "scripts/remote_install_"


def run_git(args: list[str], *, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {(proc.stderr or proc.stdout).strip()}")
    return proc.stdout.strip()


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def is_behavior_rule_path(path: str) -> bool:
    rel = normalize_path(path)
    if rel in BEHAVIOR_EXACT:
        return True
    if rel.startswith(BEHAVIOR_REMOTE_INSTALL_PREFIX):
        return True
    return any(rel.startswith(prefix) for prefix in BEHAVIOR_PREFIXES)


def changed_files() -> list[str]:
    # Includes unstaged, staged, and untracked files.
    lines = run_git(["status", "--porcelain"], check=True).splitlines()
    files: list[str] = []
    for line in lines:
        if not line:
            continue
        body = line[3:] if line[:2] == "??" else line[2:].strip()
        if " -> " in body:
            body = body.rsplit(" -> ", 1)[1]
        files.append(normalize_path(body.strip()))
    return files


def behavior_changes_in_worktree() -> list[str]:
    return [path for path in changed_files() if is_behavior_rule_path(path)]


def verify_no_uncommitted_behavior_changes() -> None:
    behavior_changes = behavior_changes_in_worktree()
    if behavior_changes:
        joined = "\n".join(f"  - {path}" for path in behavior_changes)
        raise SystemExit(
            "OPENCLAW_BEHAVIOR_RULE_GATE_FAIL: behavior-shaping files have uncommitted changes.\n"
            "Commit and push them before treating the rule as deployed:\n"
            f"{joined}"
        )


def verify_head_pushed(remote_ref: str) -> None:
    run_git(["fetch", "origin", "--prune"], check=True)
    head = run_git(["rev-parse", "HEAD"], check=True)
    remote = run_git(["rev-parse", remote_ref], check=True)
    if head != remote:
        ahead = run_git(["rev-list", "--left-right", "--count", f"HEAD...{remote_ref}"], check=True)
        raise SystemExit(
            "OPENCLAW_BEHAVIOR_RULE_GATE_FAIL: local HEAD is not exactly the remote deployment ref.\n"
            f"HEAD={head}\n{remote_ref}={remote}\nleft_right_count={ahead}\n"
            "Push or pull/rebase before deploying OpenClaw behavior rules."
        )


def verify_remote_head(expected_head: str, remote_head: str) -> None:
    if expected_head != remote_head:
        raise SystemExit(
            "OPENCLAW_BEHAVIOR_RULE_GATE_FAIL: host checkout has not pulled the expected rule commit.\n"
            f"expected={expected_head}\nremote={remote_head}"
        )


def verify_intent_registry() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/openclaw/verify_intent_tool_registry.py"],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stdout.strip())


def verify_harness_registry() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/openclaw/verify_harness_registry.py"],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stdout.strip())


def verify_js_patch_syntax_gates() -> None:
    offenders: list[str] = []
    patch_paths = {REPO / "scripts" / "openclaw" / "patch_discord_timescar_dm_preroute.py"}
    patch_paths.update(REPO / path for path in changed_files() if path.startswith("scripts/openclaw/patch_") and path.endswith(".py"))
    for path in sorted(patch_paths):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "dist" in text and "node\", \"--check\"" not in text and "node --check" not in text:
            offenders.append(normalize_path(str(path.relative_to(REPO))))
    if offenders:
        joined = "\n".join(f"  - {path}" for path in offenders)
        raise SystemExit(
            "OPENCLAW_BEHAVIOR_RULE_GATE_FAIL: dist patch scripts must run node --check or equivalent syntax gate.\n"
            f"{joined}"
        )


def remote_rev_parse(host: str, port: int, user: str, repo_path: str) -> str:
    try:
        import paramiko
    except ImportError as exc:
        raise SystemExit("paramiko is required for --verify-remote-pull") from exc

    scripts = REPO / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint

    password = load_openclaw_ssh_password()
    if not password:
        raise SystemExit(missing_password_hint())
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port=port, username=user, password=password, timeout=20)
    try:
        cmd = f"cd {repo_path} && git rev-parse HEAD && git status --short"
        stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        rc = stdout.channel.recv_exit_status()
        if rc != 0:
            raise SystemExit(f"remote git check failed ({rc}): {err or out}")
        lines = out.splitlines()
        remote_head = lines[0].strip() if lines else ""
        dirty = "\n".join(lines[1:]).strip()
        if dirty:
            raise SystemExit(
                "OPENCLAW_BEHAVIOR_RULE_GATE_FAIL: host checkout is dirty after pull.\n"
                f"{dirty}"
            )
        return remote_head
    finally:
        client.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mechanical gate for OpenClaw behavior-shaping rules: Git first, host pull second."
    )
    parser.add_argument("--remote-ref", default="origin/main")
    parser.add_argument("--skip-pushed-check", action="store_true")
    parser.add_argument("--verify-remote-pull", action="store_true")
    parser.add_argument("--host", default=os.environ.get("OPENCLAW_SSH_HOST", "ccnode.briconbric.com"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("OPENCLAW_SSH_PORT", "8822")))
    parser.add_argument("--user", default=os.environ.get("OPENCLAW_SSH_USER", "root"))
    parser.add_argument("--repo-path", default="/var/lib/openclaw/repos/SpringMonkey")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    verify_no_uncommitted_behavior_changes()
    verify_intent_registry()
    verify_harness_registry()
    verify_js_patch_syntax_gates()
    if not args.skip_pushed_check:
        verify_head_pushed(args.remote_ref)
    head = run_git(["rev-parse", "HEAD"], check=True)
    if args.verify_remote_pull:
        remote_head = remote_rev_parse(args.host, args.port, args.user, args.repo_path)
        verify_remote_head(head, remote_head)
    print(f"openclaw_behavior_rule_gate_ok head={head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
