#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import long_task_supervisor as supervisor


TERMINAL_FAILURE_STATUSES = {"failed", "timed_out", "delivery_failed"}
ACTIVE_STATUSES = {"running", "final_detected", "delivery_queued"}


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def run_git(repo_root: Path, args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    return proc.returncode, (proc.stdout or "").strip()


def resolve_repo_root(repo_root: Path) -> Path:
    if repo_root.is_dir():
        return repo_root
    cwd = Path.cwd()
    if (cwd / ".git").exists():
        return cwd
    return repo_root


def check_git(repo_root: Path, *, fetch: bool) -> list[CheckResult]:
    repo_root = resolve_repo_root(repo_root)
    results: list[CheckResult] = []
    results.append(CheckResult("git_repo_root", repo_root.is_dir(), str(repo_root)))
    if not repo_root.is_dir():
        return results
    if fetch:
        code, output = run_git(repo_root, ["fetch", "origin"])
        results.append(CheckResult("git_fetch_origin", code == 0, output or f"exit={code}"))
    code, head = run_git(repo_root, ["rev-parse", "HEAD"])
    results.append(CheckResult("git_head_readable", code == 0 and bool(head), head or f"exit={code}"))
    code, origin = run_git(repo_root, ["rev-parse", "origin/main"])
    results.append(CheckResult("git_origin_main_readable", code == 0 and bool(origin), origin or f"exit={code}"))
    if head and origin:
        results.append(CheckResult("git_head_matches_origin_main", head == origin, f"HEAD={head[:12]} origin/main={origin[:12]}"))
    code, status = run_git(repo_root, ["status", "--short"])
    results.append(CheckResult("git_worktree_clean", code == 0 and not status, status or "clean"))
    return results


def recompute_domain_task(task: dict[str, Any]) -> tuple[str, str]:
    stdout = supervisor.read_text_limited(str(task.get("stdout_file") or ""))
    if not stdout:
        return "unknown", "no stdout"
    repo_root = Path(str(task.get("repo_root") or supervisor.DEFAULT_REPO_ROOT))
    return supervisor.domain_implementation_report_status(stdout, repo_root=repo_root)


def check_long_tasks(state_path: Path, *, allow_active: bool) -> list[CheckResult]:
    state = supervisor.read_state(state_path)
    tasks = state.get("tasks") if isinstance(state.get("tasks"), list) else []
    results: list[CheckResult] = []

    active = [task for task in tasks if str(task.get("status") or "") in ACTIVE_STATUSES]
    results.append(
        CheckResult(
            "long_tasks_no_active_or_pending",
            allow_active or not active,
            f"active={len(active)}" if active else "none",
        )
    )

    delivery_failed = [task for task in tasks if str(task.get("status") or "") == "delivery_failed"]
    results.append(
        CheckResult(
            "long_tasks_no_delivery_failed",
            not delivery_failed,
            f"delivery_failed={len(delivery_failed)}" if delivery_failed else "none",
        )
    )

    false_negatives: list[str] = []
    for task in tasks:
        if str(task.get("source") or "") != "domain_implementation":
            continue
        if str(task.get("result_status") or "") != "failed" and str(task.get("status") or "") not in TERMINAL_FAILURE_STATUSES:
            continue
        status, detail = recompute_domain_task(task)
        if status == "success":
            false_negatives.append(str(task.get("run_id") or task.get("task_id") or "unknown"))
        elif status == "failed" and not str(task.get("final_report") or "").strip():
            false_negatives.append(f"{task.get('run_id') or task.get('task_id')}:failed_without_final_report:{detail[:80]}")

    results.append(
        CheckResult(
            "long_tasks_no_success_misclassified_as_failed",
            not false_negatives,
            "none" if not false_negatives else ", ".join(false_negatives[:10]),
        )
    )
    return results


def check_service(*, skip_service: bool) -> list[CheckResult]:
    if skip_service:
        return []
    proc = subprocess.run(
        ["systemctl", "is-active", "openclaw.service"],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=20,
    )
    output = (proc.stdout or "").strip()
    return [CheckResult("openclaw_service_active", proc.returncode == 0 and output == "active", output or f"exit={proc.returncode}")]


def check_gauntlet(gauntlet_root: Path) -> list[CheckResult]:
    path = gauntlet_root / "self_evolution_gauntlet.jsonl"
    if not path.is_file():
        return [CheckResult("self_evolution_gauntlet_present", False, f"missing {path}")]
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    scenarios = {str(row.get("scenario") or ""): row for row in rows if row.get("ok") is True}
    required = {"readonly-helper-regression", "write-tool-regression"}
    missing = sorted(required - set(scenarios))
    commits = [str(row.get("commit") or "") for row in scenarios.values()]
    changed_ok = all(row.get("changed_files") for row in scenarios.values())
    return [
        CheckResult("self_evolution_gauntlet_present", True, str(path)),
        CheckResult("self_evolution_gauntlet_scenarios", not missing, "ok" if not missing else "missing=" + ",".join(missing)),
        CheckResult("self_evolution_gauntlet_commits", all(commits), ",".join(item[:12] for item in commits if item) or "none"),
        CheckResult("self_evolution_gauntlet_changed_files", changed_ok, "ok" if changed_ok else "missing changed files"),
    ]


def emit(results: list[CheckResult], *, json_output: bool) -> None:
    payload = {"ok": all(item.ok for item in results), "checks": [item.__dict__ for item in results]}
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for item in results:
        status = "ok" if item.ok else "FAIL"
        print(f"{status} {item.name}: {item.detail}")
    print("self_evolution_closure_ok" if payload["ok"] else "self_evolution_closure_failed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify self-evolution end-to-end closure invariants.")
    parser.add_argument("--repo-root", type=Path, default=supervisor.DEFAULT_REPO_ROOT)
    parser.add_argument("--state", type=Path, default=supervisor.DEFAULT_STATE_PATH)
    parser.add_argument("--fetch", action="store_true", help="Fetch origin before comparing HEAD and origin/main.")
    parser.add_argument("--allow-active", action="store_true", help="Allow active long tasks during an in-progress smoke.")
    parser.add_argument("--skip-service", action="store_true", help="Skip systemd service check for local tests.")
    parser.add_argument("--require-gauntlet", action="store_true", help="Require recent controlled self-evolution gauntlet records.")
    parser.add_argument("--gauntlet-root", type=Path, default=supervisor.WORKSPACE / "agent_society_kernel")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    results: list[CheckResult] = []
    results.extend(check_git(args.repo_root, fetch=args.fetch))
    results.extend(check_long_tasks(args.state, allow_active=args.allow_active))
    results.extend(check_service(skip_service=args.skip_service))
    if args.require_gauntlet:
        results.extend(check_gauntlet(args.gauntlet_root))
    emit(results, json_output=args.json)
    return 0 if all(item.ok for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
