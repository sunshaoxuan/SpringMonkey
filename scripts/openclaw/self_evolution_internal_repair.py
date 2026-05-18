#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_REPO = Path(__file__).resolve().parents[2]
DEFAULT_RUN_DIR = Path("/var/lib/openclaw/.openclaw/workspace/state/self_evolution_runs")
DEFAULT_VERIFY_COMMANDS = [
    "python -m compileall -q scripts/openclaw/self_evolution_internal_repair.py scripts/openclaw/test_self_evolution_internal_repair.py scripts/openclaw/test_self_evolution_internal_repair_registry.py scripts/openclaw/intent_tool_router.py",
    "python scripts/openclaw/test_self_evolution_internal_repair.py",
    "python scripts/openclaw/test_self_evolution_internal_repair_registry.py",
    "python scripts/openclaw/verify_intent_tool_registry.py",
    "python scripts/openclaw/verify_harness_registry.py",
    "python scripts/openclaw/verify_capability_baseline.py",
]


@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout_tail: str
    stderr_tail: str


@dataclass
class BoundaryDecision:
    internal_write_allowed: bool
    private_verification_allowed: bool
    git_push_allowed: bool
    public_release_requires_approval: bool
    external_effect_requires_approval: bool
    reasons: list[str]


@dataclass
class SelfEvolutionRunResult:
    implementation_run_id: str
    status: str
    stage: str
    repo_root: str
    package_id: str
    changed_files: list[str]
    verify_results: list[dict[str, Any]]
    pushed: bool
    commit: str
    retry_allowed: bool
    retry_reason: str
    boundary: dict[str, Any]
    approval_package: str
    run_record: str
    evidence: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def tail(text: str, limit: int = 1800) -> str:
    return (text or "")[-limit:]


def read_package(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"error": f"package_state_not_found: {path}"}


def package_id_from_state(package_state: dict[str, Any]) -> str:
    return str(package_state.get("package_id") or package_state.get("tool_id") or "")


def decide_boundary(text: str, reason: str = "", package_state: dict[str, Any] | None = None) -> BoundaryDecision:
    package_json = json.dumps(package_state or {}, ensure_ascii=False)
    # Internal-repair evidence may come from the repair package, but public/external
    # side-effect detection must be based on the requested work itself. Repair
    # packages often contain policy prose such as "must not use credentials" or
    # "no external production side effect was requested"; treating those guardrail
    # sentences as requested effects caused valid private verification runs to exit 2.
    internal_haystack = "\n".join([text or "", reason or "", package_json])
    requested_effect_haystack = "\n".join([text or "", reason or ""])
    internal_markers = ["自增益", "自演进", "self", "internal", "能力补齐", "仓库", "repo", "测试", "验证", "verify"]
    public_markers = ["公共频道", "公开", "public", "发布", "release", "announce"]
    external_markers = ["预约", "支付", "删除", "凭据", "credential", "login", "第三方", "外部生产"]
    internal = any(marker.lower() in internal_haystack.lower() for marker in internal_markers)
    public = any(marker.lower() in requested_effect_haystack.lower() for marker in public_markers)
    external = any(marker.lower() in requested_effect_haystack.lower() for marker in external_markers)
    reasons: list[str] = []
    if internal:
        reasons.append("owner-controlled internal implementation/verification detected")
    if public:
        reasons.append("public/channel release must be approval-gated")
    if external:
        reasons.append("external production side effects must be approval-gated")
    return BoundaryDecision(
        internal_write_allowed=internal,
        private_verification_allowed=internal,
        git_push_allowed=internal and not external,
        public_release_requires_approval=public,
        external_effect_requires_approval=external,
        reasons=reasons or ["no autonomous internal repair boundary detected"],
    )


def run_command(command: str, repo_root: Path) -> CommandResult:
    proc = subprocess.run(
        command,
        cwd=repo_root,
        shell=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=420,
    )
    return CommandResult(command=command, returncode=proc.returncode, stdout_tail=tail(proc.stdout), stderr_tail=tail(proc.stderr))


def git_changed_files(repo_root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    files: list[str] = []
    for line in proc.stdout.splitlines():
        item = line[3:].strip()
        if item:
            files.append(item)
    return files


def commit_and_push(repo_root: Path, implementation_run_id: str, changed_files: list[str]) -> tuple[bool, str, str]:
    if not changed_files:
        return False, "", "no changes to push"
    fetch = run_command("git fetch origin", repo_root)
    if fetch.returncode != 0:
        return False, "", f"git fetch origin failed: {fetch.stderr_tail or fetch.stdout_tail}"
    rebase = run_command("git pull --rebase origin main", repo_root)
    if rebase.returncode != 0:
        return False, "", f"git pull --rebase origin main failed: {rebase.stderr_tail or rebase.stdout_tail}"
    add = run_command("git add config/openclaw/intent_tools.json scripts/openclaw/intent_tool_router.py scripts/openclaw/self_evolution_internal_repair.py scripts/openclaw/test_self_evolution_internal_repair.py scripts/openclaw/test_self_evolution_internal_repair_registry.py", repo_root)
    if add.returncode != 0:
        return False, "", f"git add failed: {add.stderr_tail or add.stdout_tail}"
    commit = run_command(f"git commit -m 'Add self evolution internal repair executor ({implementation_run_id})'", repo_root)
    if commit.returncode != 0:
        return False, "", f"git commit failed: {commit.stderr_tail or commit.stdout_tail}"
    rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    push = run_command("git push origin main", repo_root)
    if push.returncode != 0:
        return False, rev.stdout.strip(), f"git push origin main failed: {push.stderr_tail or push.stdout_tail}"
    return True, rev.stdout.strip(), "pushed"


def write_approval_package(run_dir: Path, implementation_run_id: str, boundary: BoundaryDecision, package_state: dict[str, Any]) -> str:
    path = run_dir / f"{implementation_run_id}_approval_required.json"
    payload = {
        "implementation_run_id": implementation_run_id,
        "created_at": utc_now(),
        "package_id": package_id_from_state(package_state),
        "held_actions": {
            "public_release": boundary.public_release_requires_approval,
            "external_effect": boundary.external_effect_requires_approval,
        },
        "allowed_without_approval": {
            "internal_repo_write": boundary.internal_write_allowed,
            "private_verification": boundary.private_verification_allowed,
            "owner_controlled_git_push": boundary.git_push_allowed,
        },
        "reason": boundary.reasons,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)


def record_run(run_dir: Path, result: SelfEvolutionRunResult) -> str:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{result.implementation_run_id}.json"
    data = asdict(result)
    data["recorded_at"] = utc_now()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)


def execute_self_evolution_run(
    *,
    implementation_run_id: str,
    text: str,
    reason: str,
    repo_root: Path,
    package_state_path: Path | None,
    run_dir: Path,
    verify_commands: list[str] | None = None,
    push: bool = False,
    dry_run: bool = False,
) -> SelfEvolutionRunResult:
    run_dir.mkdir(parents=True, exist_ok=True)
    package_state = read_package(package_state_path)
    boundary = decide_boundary(text, reason, package_state)
    approval_package = ""
    if boundary.public_release_requires_approval or boundary.external_effect_requires_approval:
        approval_package = write_approval_package(run_dir, implementation_run_id, boundary, package_state)
    if not boundary.internal_write_allowed or boundary.external_effect_requires_approval:
        result = SelfEvolutionRunResult(
            implementation_run_id=implementation_run_id,
            status="blocked",
            stage="boundary_blocked",
            repo_root=str(repo_root),
            package_id=package_id_from_state(package_state),
            changed_files=git_changed_files(repo_root) if repo_root.exists() else [],
            verify_results=[],
            pushed=False,
            commit="",
            retry_allowed=False,
            retry_reason="blocked by safety boundary",
            boundary=asdict(boundary),
            approval_package=approval_package,
            run_record="",
            evidence="; ".join(boundary.reasons),
        )
        result.run_record = record_run(run_dir, result)
        return result
    commands = verify_commands or DEFAULT_VERIFY_COMMANDS
    verify_results = [] if dry_run else [asdict(run_command(command, repo_root)) for command in commands]
    verify_ok = (not dry_run) and all(item["returncode"] == 0 for item in verify_results)
    changed = git_changed_files(repo_root)
    pushed = False
    commit = ""
    push_evidence = ""
    if push and verify_ok and boundary.git_push_allowed:
        pushed, commit, push_evidence = commit_and_push(repo_root, implementation_run_id, changed)
    status = "passed" if verify_ok and ((not push) or pushed or not git_changed_files(repo_root)) else "failed"
    stage = "verified" if verify_ok else "verify_failed"
    if dry_run:
        status = "planned"
        stage = "dry_run"
    elif push and verify_ok:
        remaining = git_changed_files(repo_root)
        stage = "pushed" if pushed else ("no_changes_to_push" if not remaining else "push_failed")
    evidence_parts = [f"{item['command']} -> {item['returncode']}" for item in verify_results]
    if push_evidence:
        evidence_parts.append(push_evidence)
    result = SelfEvolutionRunResult(
        implementation_run_id=implementation_run_id,
        status=status,
        stage=stage,
        repo_root=str(repo_root),
        package_id=package_id_from_state(package_state),
        changed_files=changed,
        verify_results=verify_results,
        pushed=pushed,
        commit=commit,
        retry_allowed=verify_ok,
        retry_reason="internal repair verified" if verify_ok else "verification failed; inspect verify_results",
        boundary=asdict(boundary),
        approval_package=approval_package,
        run_record="",
        evidence="; ".join(evidence_parts),
    )
    result.run_record = record_run(run_dir, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Generic owner-controlled self-evolution internal repair executor")
    parser.add_argument("--implementation-run-id", default="")
    parser.add_argument("--text", required=True)
    parser.add_argument("--reason", default="")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO))
    parser.add_argument("--package-state", default="")
    parser.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR))
    parser.add_argument("--verify-command", action="append", default=[])
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    run_id = args.implementation_run_id or f"impl_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    result = execute_self_evolution_run(
        implementation_run_id=run_id,
        text=args.text,
        reason=args.reason,
        repo_root=Path(args.repo_root),
        package_state_path=Path(args.package_state) if args.package_state else None,
        run_dir=Path(args.run_dir),
        verify_commands=args.verify_command or None,
        push=args.push,
        dry_run=args.dry_run,
    )
    payload = asdict(result)
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["evidence"])
    return 0 if result.status in {"passed", "planned"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
