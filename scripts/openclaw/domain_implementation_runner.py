#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from long_task_supervisor import ACTIVE_STATUSES, DEFAULT_STATE_PATH, read_state, register_task, upsert_task


DEFAULT_KERNEL_ROOT = Path("/var/lib/openclaw/.openclaw/workspace/agent_society_kernel")
DEFAULT_RUN_DIR = Path("/var/lib/openclaw/.openclaw/workspace/state/domain_implementation_runs")
DEFAULT_TIMEOUT_SECONDS = 7200
DEFAULT_MODEL = "ollama/qwen3:14b"

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_run_id(package_id: str, fingerprint: str = "") -> str:
    seed = f"{package_id}:{fingerprint}"
    return "impl_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


@dataclass
class DomainImplementationRun:
    run_id: str
    package_id: str
    status: str
    stage: str
    job_name: str
    started_at: str
    pid: int
    prompt_file: str
    stdout_file: str
    stderr_file: str
    long_task_id: str
    evidence: str = ""


def load_package(package_state: Path) -> dict[str, Any]:
    if not package_state.is_file():
        raise FileNotFoundError(f"package state not found: {package_state}")
    data = json.loads(package_state.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"package state is not a JSON object: {package_state}")
    return data


def existing_run(run_id: str, *, state_path: Path = DEFAULT_STATE_PATH) -> dict[str, Any] | None:
    for task in read_state(state_path).get("tasks", []):
        if isinstance(task, dict) and str(task.get("run_id") or "") == run_id:
            return task
    return None


def build_prompt(
    *,
    package: dict[str, Any],
    text: str,
    reason: str,
    run_id: str,
    repo_root: Path,
) -> str:
    package_view = {
        "package_id": package.get("package_id"),
        "status": package.get("status"),
        "gap_type": package.get("gap_type"),
        "safety_class": package.get("safety_class"),
        "tool_id": package.get("tool_id"),
        "permission_scope": package.get("permission_scope"),
        "write_operation": package.get("write_operation"),
        "replay_policy": package.get("replay_policy"),
        "reason": package.get("reason"),
        "files": package.get("files"),
    }
    return "\n".join(
        [
            "你是汤猴内部自增益实现 agent。请执行一个通用能力补齐 run，不要把具体用户任务硬编码成路由规则。",
            "",
            f"implementation_run_id: {run_id}",
            f"repo_root: {repo_root}",
            "",
            "原始请求：",
            text.strip(),
            "",
            "失败原因：",
            reason.strip(),
            "",
            "repair package：",
            json.dumps(package_view, ensure_ascii=False, indent=2, sort_keys=True),
            "",
            "必须遵守的闭环：",
            "1. 先定位缺的是能力契约、工具注册、执行器、测试、长任务收口，还是权限/外部副作用边界。",
            "2. 只允许自动修改仓库内的通用自增益、契约、测试、状态收口代码；不得把当前业务文本写成关键字分支。",
            "3. 如果需要外部生产写入、公开频道替换、凭据、第三方授权、删除或真实预约变更，只生成授权包和测试，不执行真实副作用。",
            "4. 能实现的内部修复必须加最小测试，并运行相关 verify 命令；失败要继续收紧，直到给出明确失败阶段和证据。",
            "5. 最终回复必须说明：修改了什么、跑了哪些验证、是否通过、是否还被安全边界阻断、原任务是否可以重试。",
            "",
            "建议验证：",
            "python -m pytest -q scripts/openclaw",
            "python scripts/openclaw/verify_intent_tool_registry.py",
            "python scripts/openclaw/verify_harness_registry.py",
            "python scripts/openclaw/verify_capability_baseline.py",
            "",
            "请现在开始实现并验证。最终答案中必须包含 implementation_run_id，便于 long_task_supervisor 收口。",
        ]
    )


def start_implementation(
    *,
    package_state: Path,
    text: str,
    reason: str,
    repo_root: Path,
    kernel_root: Path = DEFAULT_KERNEL_ROOT,
    state_path: Path = DEFAULT_STATE_PATH,
    run_dir: Path = DEFAULT_RUN_DIR,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    model: str | None = None,
    thinking: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> DomainImplementationRun:
    package = load_package(package_state)
    package_id = str(package.get("package_id") or package_state.parent.name)
    base_run_id = stable_run_id(package_id, str(package.get("fingerprint") or ""))
    run_id = base_run_id
    if force:
        run_id = f"{base_run_id}_r{datetime.now(timezone.utc).strftime('%H%M%S')}"
    prior = None if force else existing_run(run_id, state_path=state_path)
    if prior and str(prior.get("status") or "") in ACTIVE_STATUSES | {"delivered", "failed", "timed_out"}:
        return DomainImplementationRun(
            run_id=run_id,
            package_id=package_id,
            status=str(prior.get("status") or "running"),
            stage=str(prior.get("stage") or "running"),
            job_name=str(prior.get("job_name") or package_id),
            started_at=str(prior.get("started_at") or ""),
            pid=int(prior.get("pid") or 0),
            prompt_file=str(prior.get("prompt_file") or ""),
            stdout_file=str(prior.get("stdout_file") or ""),
            stderr_file=str(prior.get("stderr_file") or ""),
            long_task_id=str(prior.get("task_id") or ""),
            evidence="existing_run_reused",
        )

    run_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = run_dir / f"{run_id}.prompt.txt"
    stdout_file = run_dir / f"{run_id}.stdout.log"
    stderr_file = run_dir / f"{run_id}.stderr.log"
    prompt = build_prompt(package=package, text=text, reason=reason, run_id=run_id, repo_root=repo_root)
    prompt_file.write_text(prompt, encoding="utf-8")

    task = register_task(
        source="domain_implementation",
        job_id=package_id,
        run_id=run_id,
        job_name=f"自增益实现：{package.get('tool_id') or package_id}",
        reply_target="owner_dm",
        original_text=text,
        timeout_seconds=timeout_seconds,
        state_path=state_path,
    )

    pid = 0
    evidence = "dry_run_registered"
    status = "running"
    stage = "implementation_agent_running"
    if not dry_run:
        selected_model = (model or os.environ.get("OPENCLAW_DOMAIN_IMPLEMENTATION_MODEL") or DEFAULT_MODEL).strip()
        selected_thinking = (
            thinking
            or os.environ.get("OPENCLAW_DOMAIN_IMPLEMENTATION_THINKING")
            or ("off" if selected_model.startswith("ollama/") else "medium")
        ).strip()
        command = [
            "openclaw",
            "--no-color",
            "agent",
            "--agent",
            "main",
            "--model",
            selected_model,
            "--message",
            prompt,
            "--timeout",
            str(timeout_seconds),
            "--thinking",
            selected_thinking,
            "--json",
        ]
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        try:
            with stdout_file.open("ab") as out, stderr_file.open("ab") as err:
                proc = subprocess.Popen(
                    command,
                    cwd=repo_root,
                    stdout=out,
                    stderr=err,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                    env=env,
                )
            pid = int(proc.pid)
            evidence = "implementation_agent_started"
        except Exception as exc:
            status = "failed"
            stage = "implementation_agent_start_failed"
            evidence = f"{type(exc).__name__}: {exc}"
            stderr_file.write_text(evidence + "\n", encoding="utf-8")

    updated = dict(task)
    updated.update(
        {
            "status": status,
            "stage": stage,
            "pid": pid,
            "prompt_file": str(prompt_file),
            "stdout_file": str(stdout_file),
            "stderr_file": str(stderr_file),
            "kernel_root": str(kernel_root),
            "delivery_state": "pending" if status == "running" else "not_applicable",
            "implementation_package_id": package_id,
            "implementation_evidence": evidence,
        }
    )
    upsert_task(updated, state_path=state_path)
    return DomainImplementationRun(
        run_id=run_id,
        package_id=package_id,
        status=status,
        stage=stage,
        job_name=str(updated.get("job_name") or package_id),
        started_at=str(updated.get("started_at") or utc_now()),
        pid=pid,
        prompt_file=str(prompt_file),
        stdout_file=str(stdout_file),
        stderr_file=str(stderr_file),
        long_task_id=str(updated.get("task_id") or ""),
        evidence=evidence,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Start a tracked generic domain implementation run for an autonomous repair package.")
    parser.add_argument("command", choices=["start"])
    parser.add_argument("--package-state", type=Path, required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--kernel-root", type=Path, default=DEFAULT_KERNEL_ROOT)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--model", default="")
    parser.add_argument("--thinking", default="")
    parser.add_argument("--force", action="store_true", help="Start a new attempt even if this package already has a tracked run.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = start_implementation(
            package_state=args.package_state,
            text=args.text,
            reason=args.reason,
            repo_root=args.repo_root,
            kernel_root=args.kernel_root,
            state_path=args.state,
            run_dir=args.run_dir,
            timeout_seconds=args.timeout_seconds,
            model=args.model or None,
            thinking=args.thinking or None,
            force=args.force,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(
            json.dumps(
                {"status": "failed", "stage": "load_or_start_failed", "error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.status in {"running", "delivered", "failed", "timed_out"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
