#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from agent_society_kernel import AgentSocietyKernel, normalize_text, utc_now


DEFAULT_KERNEL_ROOT = Path("/var/lib/openclaw/.openclaw/workspace/agent_society_kernel")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a cron job through the agent-society job orchestrator.")
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--category", default="generic")
    parser.add_argument("--prompt-file")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--delivery-channel", default="")
    parser.add_argument("--delivery-to", default="")
    parser.add_argument("--kernel-root", default=str(DEFAULT_KERNEL_ROOT))
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--command", nargs=argparse.REMAINDER, required=True)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        raise SystemExit("Missing command after --command")
    return args


def load_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    return args.prompt


def build_session_request(*, job_name: str, category: str, prompt: str, command: list[str]) -> str:
    return "\n".join(
        [
            f"job_name: {job_name}",
            f"category: {category}",
            "execution_model: intent -> task -> step -> action/tool -> observation -> repair -> retry",
            f"command: {' '.join(command)}",
            "prompt:",
            prompt,
        ]
    )


def ensure_session(kernel: AgentSocietyKernel, *, job_name: str, category: str, prompt: str, command: list[str]) -> tuple[object, object]:
    request = build_session_request(job_name=job_name, category=category, prompt=prompt, command=command)
    session = kernel.bootstrap_session(request, channel=f"cron:{job_name}", user_id=job_name)
    step = kernel.next_step(session)
    if step is None:
        raise RuntimeError("kernel did not create an executable step")
    step.summary = normalize_text(f"Execute cron job action for {job_name}")
    step.chosen_tool = " ".join(command)
    if step.chosen_tool not in step.tool_candidates:
        step.tool_candidates = [step.chosen_tool] + step.tool_candidates
    step.expected_observation = normalize_text(
        f"command exits successfully and produces the final {category} output for delivery to {job_name}"
    )
    step.next_decision = "execute command and inspect stdout/stderr before deciding completion or repair"
    step.shared_context_keys = kernel._shared_context_keys_for_category(job_name, category)
    step.context_policy = "reuse"
    step.action_kind = "tool"
    step.status = "in_progress"
    step.updated_at = utc_now()
    kernel.save_session(session)
    return session, step


def run_command(command: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
    )


def render_observation(result: subprocess.CompletedProcess[str] | None, error: BaseException | None = None) -> str:
    if error is not None:
        return f"command failed with exception: {type(error).__name__}: {error}"
    assert result is not None
    return json.dumps(
        {
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-2000:],
            "stderr_tail": result.stderr[-2000:],
        },
        ensure_ascii=False,
    )


def record_gap_via_runtime(
    *,
    repo_root: Path,
    kernel_root: Path,
    job_name: str,
    prompt: str,
    observation: str,
    failure_status: str,
) -> dict:
    script = repo_root / "scripts" / "openclaw" / "agent_society_runtime_record_gap.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(kernel_root),
            "--repo-root",
            str(repo_root),
            "--channel",
            f"cron:{job_name}",
            "--user-id",
            job_name,
            "--prompt",
            prompt,
            "--observation",
            observation,
            "--failure-status",
            failure_status,
            "--next-decision",
            "record cron job failure, create bounded repair if reusable, then retry the original step once",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return json.loads(proc.stdout)


def main() -> int:
    args = parse_args()
    prompt = load_prompt(args)
    kernel_root = Path(args.kernel_root)
    repo_root = Path(args.repo_root)
    kernel = AgentSocietyKernel(kernel_root)
    session_request = build_session_request(job_name=args.job_name, category=args.category, prompt=prompt, command=args.command)
    session, step = ensure_session(
        kernel,
        job_name=args.job_name,
        category=args.category,
        prompt=prompt,
        command=args.command,
    )

    attempts: list[dict[str, object]] = []
    for attempt in range(args.max_retries + 1):
        result: subprocess.CompletedProcess[str] | None = None
        error: BaseException | None = None
        try:
            result = run_command(args.command, args.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            error = exc
        observation = render_observation(result, error)
        attempts.append({"attempt": attempt + 1, "observation": observation})

        if result is not None and result.returncode == 0:
            session = kernel.load_session(session.session_id)
            kernel.record_observation(
                session,
                step.step_id,
                observation,
                "command succeeded; preserve stdout as final delivery payload",
                "completed",
            )
            session = kernel.load_session(session.session_id)
            report_step = next((item for item in session.steps if item.action_kind == "report" and item.status == "pending"), None)
            if report_step is not None:
                kernel.record_observation(
                    session,
                    report_step.step_id,
                    f"stdout bytes={len(result.stdout.encode('utf-8'))}",
                    "final delivery payload preserved without changing stdout contract",
                    "completed",
                )
            sys.stdout.write(result.stdout)
            if result.stdout and not result.stdout.endswith("\n"):
                sys.stdout.write("\n")
            return 0

        session = kernel.load_session(session.session_id)
        kernel.record_observation(
            session,
            step.step_id,
            observation,
            "command failed; classify gap and prepare bounded self-repair before retry",
            "blocked",
        )
        record_gap_via_runtime(
            repo_root=repo_root,
            kernel_root=kernel_root,
            job_name=args.job_name,
            prompt=session_request,
            observation=observation,
            failure_status="blocked",
        )
        if attempt < args.max_retries:
            continue

    final = {
        "status": "failed",
        "job": args.job_name,
        "category": args.category,
        "message": "Job orchestrator exhausted bounded retry after recording self-repair evidence.",
        "attempts": attempts,
        "session_id": session.session_id,
    }
    print(json.dumps(final, ensure_ascii=False, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
