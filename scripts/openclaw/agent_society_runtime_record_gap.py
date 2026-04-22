#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from agent_society_helper_toolsmith import normalize_slug
from agent_society_kernel import AgentSocietyKernel


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
    if gap.proposed_tool_name:
        helpers_dir = repo_root / "scripts" / "openclaw" / "helpers"
        helpers_dir.mkdir(parents=True, exist_ok=True)
        slug = normalize_slug(gap.proposed_tool_name)
        helper_path = helpers_dir / f"{slug}.py"
        if not helper_path.exists():
            helper_path.write_text(
                "#!/usr/bin/env python3\n"
                "from __future__ import annotations\n\n"
                "import json\n\n"
                "def main() -> int:\n"
                f"    print(json.dumps({{'helper_name': {gap.proposed_tool_name!r}, 'status': 'scaffold', 'purpose': {gap.proposed_repair!r}}}, ensure_ascii=False))\n"
                "    return 0\n\n"
                "if __name__ == '__main__':\n"
                "    raise SystemExit(main())\n",
                encoding="utf-8",
            )
            helper_path.chmod(0o755)
        session = kernel.load_session(session.session_id)
        tool = kernel.propose_helper_from_gap(
            session,
            gap.gap_id,
            "script",
            str(helper_path.relative_to(repo_root)).replace("\\", "/"),
            scope=gap.category,
            notes=gap.proposed_repair,
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
