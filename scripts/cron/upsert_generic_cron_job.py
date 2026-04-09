#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

JOBS_PATH = Path("/var/lib/openclaw/.openclaw/cron/jobs.json")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Create, update, verify, or delete generic OpenClaw cron jobs via the official Gateway CLI.",
    )
    p.add_argument("--name", required=True, help="Stable job name.")
    p.add_argument("--delete", action="store_true", help="Delete the named job instead of upserting it.")
    p.add_argument("--description", default="", help="Human-readable description.")
    p.add_argument("--expr", help="Cron expression, for example: 0 7 * * 1-5")
    p.add_argument("--tz", default="Asia/Tokyo", help="Cron timezone.")
    p.add_argument("--message-file", help="UTF-8 file containing the exact agentTurn message.")
    p.add_argument("--message", help="Exact agentTurn message.")
    p.add_argument("--delivery-channel", help="Delivery channel such as discord or line.")
    p.add_argument("--delivery-to", help="Delivery target, for example channel ID or LINE user ID.")
    p.add_argument("--delivery-mode", default="announce", help="Delivery mode. Default: announce.")
    p.add_argument("--delivery-account-id", default="default", help="Gateway accountId. Default: default.")
    p.add_argument("--model", default="ollama/qwen3:14b", help="Task model. Default keeps qwen primary.")
    p.add_argument("--thinking", default="low", help="Thinking setting. Default: low.")
    p.add_argument("--timeout-seconds", type=int, default=900, help="Task timeout seconds. Default: 900.")
    p.add_argument("--light-context", choices=["true", "false"], default="true")
    p.add_argument("--disabled", action="store_true", help="Create/update the job but leave it disabled.")
    p.add_argument("--agent-id", default="main", help="Target agent id. Default: main.")
    p.add_argument("--session-target", default="isolated", help="Session target. Default: isolated.")
    p.add_argument("--wake-mode", default="now", help="Wake mode. Default: now.")
    p.add_argument("--verify-only", action="store_true", help="Do not write. Only print the current matching job JSON.")
    return p.parse_args()


def require_non_empty(value: str | None, flag: str) -> str:
    if value and value.strip():
        return value
    raise SystemExit(f"Missing required argument: {flag}")


def load_message(args: argparse.Namespace) -> str:
    if args.message_file:
        return Path(args.message_file).read_text(encoding="utf-8")
    if args.message:
        return args.message
    raise SystemExit("One of --message-file or --message is required.")


def bool_arg(value: str) -> bool:
    return value.lower() == "true"


def openclaw_prefix() -> list[str]:
    home = "/var/lib/openclaw"
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return ["runuser", "-u", "openclaw", "--", "env", f"HOME={home}", "openclaw"]
    env_home = os.environ.get("HOME")
    if env_home != home:
        os.environ["HOME"] = home
    return ["openclaw"]


def run_openclaw(args: list[str]) -> tuple[str, str, int]:
    proc = subprocess.run(
        openclaw_prefix() + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.stdout, proc.stderr, proc.returncode


def load_jobs_file() -> list[dict]:
    if not JOBS_PATH.exists():
        return []
    data = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
    return data.get("jobs", [])


def find_job_by_name(name: str) -> dict | None:
    for job in load_jobs_file():
        if job.get("name") == name:
            return job
    return None


def render_job(job: dict | None) -> int:
    if not job:
        print("JOB_NOT_FOUND")
        return 2
    print(json.dumps(job, ensure_ascii=False, indent=2))
    return 0


def build_add_args(args: argparse.Namespace, message: str) -> list[str]:
    cli = [
        "cron",
        "add",
        "--name",
        args.name,
        "--cron",
        require_non_empty(args.expr, "--expr"),
        "--tz",
        args.tz,
        "--agent",
        args.agent_id,
        "--session",
        args.session_target,
        "--wake",
        args.wake_mode,
        "--message",
        message,
        "--model",
        args.model,
        "--thinking",
        args.thinking,
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--announce",
        "--channel",
        require_non_empty(args.delivery_channel, "--delivery-channel"),
        "--to",
        require_non_empty(args.delivery_to, "--delivery-to"),
        "--account",
        args.delivery_account_id,
        "--json",
    ]
    if args.description:
        cli.extend(["--description", args.description])
    if bool_arg(args.light_context):
        cli.append("--light-context")
    if args.disabled:
        cli.append("--disabled")
    return cli


def build_edit_args(job_id: str, args: argparse.Namespace, message: str) -> list[str]:
    cli = [
        "cron",
        "edit",
        job_id,
        "--name",
        args.name,
        "--cron",
        require_non_empty(args.expr, "--expr"),
        "--tz",
        args.tz,
        "--agent",
        args.agent_id,
        "--session",
        args.session_target,
        "--wake",
        args.wake_mode,
        "--message",
        message,
        "--model",
        args.model,
        "--thinking",
        args.thinking,
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--channel",
        require_non_empty(args.delivery_channel, "--delivery-channel"),
        "--to",
        require_non_empty(args.delivery_to, "--delivery-to"),
        "--account",
        args.delivery_account_id,
    ]
    if args.description:
        cli.extend(["--description", args.description])
    if bool_arg(args.light_context):
        cli.append("--light-context")
    else:
        cli.append("--no-light-context")
    if args.disabled:
        cli.append("--disable")
        cli.append("--no-deliver")
    else:
        cli.append("--enable")
        cli.append("--announce")
    return cli


def main() -> int:
    args = parse_args()
    existing = find_job_by_name(args.name)

    if args.verify_only:
        return render_job(existing)

    if args.delete:
        if not existing:
            print(json.dumps({"deleted": False, "name": args.name}, ensure_ascii=False))
            return 0
        stdout, stderr, rc = run_openclaw(["cron", "rm", existing["id"], "--json"])
        if rc != 0:
            raise SystemExit(f"openclaw cron rm failed ({rc}): {(stderr or stdout).strip()}")
        print(stdout.strip())
        return 0

    message = load_message(args)
    if existing:
        cli_args = build_edit_args(existing["id"], args, message)
    else:
        cli_args = build_add_args(args, message)

    stdout, stderr, rc = run_openclaw(cli_args)
    if rc != 0:
        raise SystemExit(f"openclaw cron write failed ({rc}): {(stderr or stdout).strip()}")

    payload = None
    if stdout.strip():
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = None
        print(stdout.strip())

    if payload and payload.get("name") == args.name:
        return 0

    job = find_job_by_name(args.name)
    if not job:
        raise SystemExit("CLI returned success but the job is still missing from jobs.json.")
    print(json.dumps(job, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
