#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from domain_implementation_runner import append_stage_event, stage_events_path, start_implementation
from long_task_supervisor import poll_tasks
from regression_repair_runner import run_regression_repair


REPO = Path(__file__).resolve().parents[2]
DEFAULT_KERNEL_ROOT = Path("/var/lib/openclaw/.openclaw/workspace/agent_society_kernel")
DEFAULT_STATE_PATH = Path("/var/lib/openclaw/.openclaw/workspace/state/long_task_supervisor/tasks.json")
SCENARIOS = {"readonly-helper-regression", "write-tool-regression"}


@dataclass
class CommandResult:
    command: str
    returncode: int
    output_tail: str


@dataclass
class GauntletResult:
    ok: bool
    scenario: str
    status: str
    worktree: str
    run_id: str
    long_task_id: str
    commit: str
    changed_files: list[str]
    verify_results: list[dict[str, Any]]
    replay_allowed: bool
    replay_reason: str
    record_path: str
    evidence: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_command(command: list[str], *, cwd: Path, timeout: int = 180) -> CommandResult:
    proc = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    output = (proc.stdout or "").strip()
    return CommandResult(" ".join(command), proc.returncode, output[-2000:])


def create_worktree(repo_root: Path, base_dir: Path) -> Path:
    worktree = base_dir / "gauntlet-worktree"
    result = run_command(["git", "worktree", "add", "--detach", str(worktree), "HEAD"], cwd=repo_root, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(result.output_tail or "git worktree add failed")
    run_command(["git", "config", "user.email", "gauntlet@springmonkey.local"], cwd=worktree)
    run_command(["git", "config", "user.name", "SpringMonkey Gauntlet"], cwd=worktree)
    return worktree


def remove_worktree(repo_root: Path, worktree: Path) -> None:
    run_command(["git", "worktree", "remove", "--force", str(worktree)], cwd=repo_root, timeout=120)


def package_state(kernel_root: Path, scenario: str) -> Path:
    package_dir = kernel_root / "gauntlet_packages" / scenario
    package_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "package_id": f"gauntlet_{scenario}",
        "status": "internal_repair_required",
        "gap_type": "gauntlet_regression",
        "safety_class": "auto_safe_readonly" if scenario == "readonly-helper-regression" else "external_side_effect_gated",
        "tool_id": "openclaw.gauntlet.synthetic",
        "permission_scope": "owner_controlled_internal_repair",
        "write_operation": scenario == "write-tool-regression",
        "external_side_effect": scenario == "write-tool-regression",
        "internal_repair_allowed": True,
        "replay_policy": "verify_before_replay" if scenario == "readonly-helper-regression" else "external_replay_gated_after_internal_repair",
        "reason": "self evolution gauntlet synthetic regression",
        "files": [],
        "fingerprint": scenario,
    }
    path = package_dir / "package_state.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_probe_files(worktree: Path, scenario: str) -> list[str]:
    slug = scenario.replace("-", "_")
    helper = worktree / "scripts" / "openclaw" / f"generated_{slug}_probe.py"
    test = worktree / "scripts" / "openclaw" / f"test_generated_{slug}_probe.py"
    helper.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "def probe() -> dict:",
                f"    return {{'status': 'ok', 'scenario': '{scenario}', 'external_effect': {str(scenario == 'write-tool-regression')}}}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    test.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                f"from generated_{slug}_probe import probe",
                "",
                "def test_gauntlet_probe_contract() -> None:",
                "    result = probe()",
                "    assert result['status'] == 'ok'",
                f"    assert result['scenario'] == '{scenario}'",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return [str(helper.relative_to(worktree)).replace("\\", "/"), str(test.relative_to(worktree)).replace("\\", "/")]


def git_changed_files(worktree: Path) -> list[str]:
    result = run_command(["git", "status", "--short", "--untracked-files=all"], cwd=worktree)
    files: list[str] = []
    for line in result.output_tail.splitlines():
        if len(line) > 3:
            files.append(line[3:].strip().replace("\\", "/"))
    return files


def commit_all(worktree: Path, message: str) -> str:
    run_command(["git", "add", "scripts/openclaw"], cwd=worktree)
    result = run_command(["git", "commit", "-m", message], cwd=worktree, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(result.output_tail or "git commit failed")
    head = run_command(["git", "rev-parse", "HEAD"], cwd=worktree)
    if head.returncode != 0:
        raise RuntimeError(head.output_tail or "git rev-parse failed")
    return head.output_tail.strip()


def append_record(kernel_root: Path, result: GauntletResult) -> Path:
    path = kernel_root / "self_evolution_gauntlet.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"created_at": utc_now(), **asdict(result)}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def run_gauntlet(
    *,
    scenario: str,
    repo_root: Path = REPO,
    kernel_root: Path = DEFAULT_KERNEL_ROOT,
    state_path: Path = DEFAULT_STATE_PATH,
    keep_worktree: bool = False,
) -> GauntletResult:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario}")
    base_dir = Path(tempfile.mkdtemp(prefix="openclaw-gauntlet-"))
    worktree = create_worktree(repo_root, base_dir)
    verify_results: list[dict[str, Any]] = []
    commit = ""
    changed_files: list[str] = []
    run_id = ""
    long_task_id = ""
    try:
        package = package_state(kernel_root, scenario)
        run = start_implementation(
            package_state=package,
            text=f"run self evolution gauntlet scenario {scenario}",
            reason="synthetic regression must be repaired with real diff, tests, commit, and baseline evidence",
            repo_root=worktree,
            kernel_root=kernel_root,
            state_path=state_path,
            run_dir=kernel_root / "gauntlet_runs",
            dry_run=True,
            force=True,
        )
        run_id = run.run_id
        long_task_id = run.long_task_id
        events = Path(run.stage_events_file) if run.stage_events_file else stage_events_path(kernel_root / "gauntlet_runs", run_id)
        append_stage_event(events, run_id=run_id, stage="diff_created", summary="gauntlet 已写入合成修复代码。")
        changed_files = write_probe_files(worktree, scenario)
        append_stage_event(events, run_id=run_id, stage="tests_started", summary="gauntlet 开始运行验证。")
        test_file = changed_files[1]
        commands = [
            [sys.executable, "-m", "pytest", "-q", test_file],
            [sys.executable, "scripts/openclaw/verify_intent_tool_registry.py"],
            [sys.executable, "scripts/openclaw/verify_harness_registry.py"],
            [sys.executable, "scripts/openclaw/verify_capability_baseline.py"],
            [sys.executable, "scripts/openclaw/verify_harness_flow_exits.py"],
        ]
        for command in commands:
            result = run_command(command, cwd=worktree, timeout=240)
            verify_results.append(asdict(result))
            if result.returncode != 0:
                append_stage_event(events, run_id=run_id, stage="tests_failed", status="failed", summary="gauntlet 验证失败。", evidence=result.output_tail)
                raise RuntimeError(result.output_tail)
        append_stage_event(events, run_id=run_id, stage="tests_passed", summary="gauntlet 验证已通过。")
        changed_files = git_changed_files(worktree)
        if not changed_files:
            raise RuntimeError("gauntlet produced no git diff")
        commit = commit_all(worktree, f"Self evolution gauntlet {scenario}")
        append_stage_event(events, run_id=run_id, stage="commit_created", summary="gauntlet 已创建可验证提交。", evidence=commit)
        if scenario == "write-tool-regression":
            regression = run_regression_repair(
                text="把这单的开始时间往后推24小时，结束时间不变。",
                stage="binding",
                reason="gauntlet synthetic write regression",
                kernel_root=kernel_root,
                registry_path=worktree / "config" / "openclaw" / "intent_tools.json",
                cases_path=worktree / "config" / "openclaw" / "capability_baseline_cases.json",
            )
            if not regression.matched or not regression.package.get("internal_repair_allowed"):
                raise RuntimeError("write regression did not produce internal repair package")
        append_stage_event(events, run_id=run_id, stage="final_succeeded", status="success", summary="gauntlet 已完成真实 diff、测试和提交。", evidence=commit)
        poll_tasks(state_path=state_path, deliver=True, repair=False, deliverer=lambda _task, _body: (True, "gauntlet_internal_delivery"))
        result = GauntletResult(
            ok=True,
            scenario=scenario,
            status="final_succeeded",
            worktree=str(worktree),
            run_id=run_id,
            long_task_id=long_task_id,
            commit=commit,
            changed_files=changed_files,
            verify_results=verify_results,
            replay_allowed=scenario == "readonly-helper-regression",
            replay_reason="readonly gauntlet may replay after verification" if scenario == "readonly-helper-regression" else "external write replay remains gated",
            record_path="",
            evidence="gauntlet completed",
        )
    except Exception as exc:
        if run_id:
            events = stage_events_path(kernel_root / "gauntlet_runs", run_id)
            append_stage_event(events, run_id=run_id, stage="final_failed", status="failed", summary="gauntlet 失败。", evidence=f"{type(exc).__name__}: {exc}")
        result = GauntletResult(
            ok=False,
            scenario=scenario,
            status="final_failed",
            worktree=str(worktree),
            run_id=run_id,
            long_task_id=long_task_id,
            commit=commit,
            changed_files=changed_files,
            verify_results=verify_results,
            replay_allowed=False,
            replay_reason="gauntlet failed",
            record_path="",
            evidence=f"{type(exc).__name__}: {exc}",
        )
    record = append_record(kernel_root, result)
    result.record_path = str(record)
    if not keep_worktree:
        remove_worktree(repo_root, worktree)
        shutil.rmtree(base_dir, ignore_errors=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a controlled self-evolution gauntlet in a temporary Git worktree.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--kernel-root", type=Path, default=DEFAULT_KERNEL_ROOT)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--worktree-temp", action="store_true", help="Compatibility flag. Gauntlet always uses a temporary worktree.")
    parser.add_argument("--keep-worktree", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_gauntlet(
        scenario=args.scenario,
        repo_root=args.repo_root,
        kernel_root=args.kernel_root,
        state_path=args.state,
        keep_worktree=args.keep_worktree,
    )
    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"self_evolution_gauntlet_{'ok' if result.ok else 'failed'} {result.scenario} {result.commit or result.evidence}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
