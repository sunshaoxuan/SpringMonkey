#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from agent_society_helper_toolsmith import create_helper_tool
from agent_society_kernel import AgentSocietyKernel, utc_now


REUSABLE_HELPER_CATEGORIES = {
    "execution_blocked",
    "runtime_drift",
    "runtime_timeout",
    "target_discovery_missing",
    "tool_missing",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Record direct-task runtime failures into the durable kernel.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--observation", required=True)
    parser.add_argument("--failure-status", default="blocked", choices=["blocked", "failed"])
    parser.add_argument("--next-decision", default="classify blocker and prepare a bounded repair path")
    args = parser.parse_args()

    kernel = AgentSocietyKernel(Path(args.root))
    prompt_norm = " ".join(args.prompt.split())
    session = None
    existing = sorted(kernel.sessions_dir.glob("session_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in existing[:30]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("channel") == args.channel and data.get("user_id") == args.user_id and " ".join(str(data.get("raw_request", "")).split()) == prompt_norm:
            session = kernel.load_session(data["session_id"])
            break
    if session is None:
        session = kernel.bootstrap_session(args.prompt, args.channel, args.user_id)

    step = kernel.next_step(session)
    if step is None:
        raise SystemExit("no active step available")

    kernel.record_observation(session, step.step_id, args.observation, args.next_decision, args.failure_status)
    session = kernel.load_session(session.session_id)
    gap = kernel.analyze_capability_gap(session, step.step_id, args.observation)

    helper_payload = None
    repo_root = Path(args.repo_root)
    if gap.category in REUSABLE_HELPER_CATEGORIES:
        helper_name = gap.proposed_tool_name
        if not helper_name:
            session = kernel.load_session(session.session_id)
            tool = kernel.propose_helper_from_gap(
                session,
                gap.gap_id,
                "script",
                "__pending_helper_entrypoint__",
                scope=gap.category,
                notes=gap.proposed_repair,
            )
            helper_name = tool.name
            session = kernel.load_session(session.session_id)
        helper_result = create_helper_tool(
            repo_root=repo_root,
            helper_name=helper_name,
            purpose=gap.proposed_repair,
            category=gap.category,
        )
        helper_entrypoint = str(helper_result["entrypoint"])
        session = kernel.load_session(session.session_id)
        existing_tool = next(
            (
                item for item in session.helper_tools
                if item.derived_from_gap_id == gap.gap_id and item.entrypoint == "__pending_helper_entrypoint__"
            ),
            None,
        )
        if existing_tool is not None:
            existing_tool.entrypoint = helper_entrypoint
            existing_tool.notes = gap.proposed_repair
            existing_tool.status = "registered"
            existing_tool.updated_at = utc_now()
            kernel.save_session(session)
            tool = existing_tool
        else:
            tool = kernel.propose_helper_from_gap(
                session,
                gap.gap_id,
                "script",
                helper_entrypoint,
                scope=gap.category,
                notes=gap.proposed_repair,
            )
        helper_cmd = [
            sys.executable,
            str(repo_root.joinpath(*helper_entrypoint.split("/"))),
            "--repo-root",
            str(repo_root),
            "--observation",
            args.observation,
        ]
        helper_run = subprocess.run(helper_cmd, capture_output=True, text=True, check=True)
        helper_output = json.loads(helper_run.stdout)
        validation_note = json.dumps(
            {
                "status": helper_output.get("status"),
                "category": helper_output.get("category"),
                "check_count": len(helper_output.get("checks", [])),
                "action_count": len(helper_output.get("suggested_actions", [])),
            },
            ensure_ascii=False,
        )
        session = kernel.load_session(session.session_id)
        tool = kernel.validate_helper_tool(
            session,
            tool.tool_id,
            observation=validation_note,
            status="validated" if helper_output.get("status") == "ready" else "registered",
        )
        helper_payload = {
            "tool_id": tool.tool_id,
            "name": tool.name,
            "entrypoint": tool.entrypoint,
            "status": tool.status,
        }

    print(json.dumps({
        "session_id": session.session_id,
        "gap_id": gap.gap_id,
        "gap_category": gap.category,
        "gap_status": gap.status,
        "helper": helper_payload,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
