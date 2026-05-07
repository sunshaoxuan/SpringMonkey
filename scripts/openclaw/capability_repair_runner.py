#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from dm_capability_gap_runner import GapRunnerResult, run_gap
from toolsmith_repair_runner import ToolsmithPackage, append_package_log, generate_repair_package, repair_fingerprint, verify_and_promote_package


DEFAULT_KERNEL_ROOT = Path("/var/lib/openclaw/.openclaw/workspace/agent_society_kernel")
REPLAYABLE_STAGES = {
    "intent",
    "binding",
    "semantic_review",
    "execute",
    "evaluate",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RepairRunnerResult:
    status: str
    stage: str
    safety_class: str
    gap_ref: str
    replay_allowed: bool
    replay_reason: str
    reply: str
    plan: dict[str, Any]
    registry_tool: dict[str, Any] | None = None
    toolsmith_package: dict[str, Any] | None = None
    event_log: str = ""
    created_at: str = ""


def event_log_path(kernel_root: Path) -> Path:
    return kernel_root / "capability_gap_events.jsonl"


def append_event(kernel_root: Path, payload: dict[str, Any]) -> Path:
    path = event_log_path(kernel_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def read_events(kernel_root: Path) -> list[dict[str, Any]]:
    path = event_log_path(kernel_root)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def upsert_event(kernel_root: Path, payload: dict[str, Any], fingerprint: str) -> Path:
    path = event_log_path(kernel_root)
    rows = read_events(kernel_root)
    replaced = False
    for index, row in enumerate(rows):
        if row.get("repair_fingerprint") == fingerprint:
            rows[index] = payload
            replaced = True
            break
    if not replaced:
        rows.append(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    return path


def is_tool_readonly(tool: dict[str, Any] | None) -> bool:
    return bool(tool) and not bool(tool.get("write_operation"))


def replay_decision(
    *,
    stage: str,
    gap_result: GapRunnerResult,
    replay_depth: int,
    registry_tool: dict[str, Any] | None,
) -> tuple[bool, str]:
    if replay_depth > 0:
        return False, "bounded replay already attempted"
    if stage not in REPLAYABLE_STAGES:
        return False, f"stage {stage} is not replayable"
    if gap_result.status != "promoted":
        return False, f"repair status is {gap_result.status}, not promoted"
    tool = registry_tool or gap_result.registry_tool
    if not is_tool_readonly(tool):
        return False, "candidate repair is not a verified read-only tool"
    return True, "verified read-only repair can be replayed once"


def package_replay_decision(*, stage: str, package: ToolsmithPackage | None, replay_depth: int) -> tuple[bool, str]:
    if replay_depth > 0:
        return False, "bounded replay already attempted"
    if stage not in REPLAYABLE_STAGES:
        return False, f"stage {stage} is not replayable"
    if package is None:
        return False, "no promoted repair package"
    if package.status != "promoted":
        return False, f"repair package status is {package.status}, not promoted"
    if package.write_operation:
        return False, "repair package is write-scoped"
    return True, "promoted read-only repair package can be replayed once"


def run_repair(
    *,
    text: str,
    channel: str,
    user_id: str,
    stage: str,
    reason: str,
    kernel_root: Path = DEFAULT_KERNEL_ROOT,
    repo_root: Path | None = None,
    execution_output: str = "",
    context: str = "",
    registry_tool: dict[str, Any] | None = None,
    forced_safety_class: str | None = None,
    forced_safety_reason: str | None = None,
    replay_depth: int = 0,
) -> RepairRunnerResult:
    repo_root = repo_root or Path(__file__).resolve().parents[2]
    intent_reason = reason
    if execution_output:
        intent_reason = f"{intent_reason}; output={execution_output[:1200]}"
    gap_result = run_gap(
        text=text,
        channel=channel,
        user_id=user_id,
        intent_reason=intent_reason,
        kernel_root=kernel_root,
        repo_root=repo_root,
        forced_safety_class=forced_safety_class,
        forced_safety_reason=forced_safety_reason,
        registry_tool=registry_tool,
    )
    replay_allowed, replay_reason = replay_decision(
        stage=stage,
        gap_result=gap_result,
        replay_depth=replay_depth,
        registry_tool=registry_tool,
    )
    status = gap_result.status
    toolsmith_package: ToolsmithPackage | None = None
    if replay_allowed:
        status = "verified"
    elif gap_result.status == "blocked":
        status = "blocked"
    elif gap_result.status == "planned":
        status = "planned"
    if not replay_allowed:
        toolsmith_package = generate_repair_package(
            text=text,
            reason=reason,
            safety_class=gap_result.safety_class,
            kernel_root=kernel_root,
            repo_root=repo_root,
            registry_tool=registry_tool or gap_result.registry_tool,
            apply_readonly=False,
        )
        if toolsmith_package.status == "generated" and toolsmith_package.safety_class == "auto_safe_readonly":
            toolsmith_package = verify_and_promote_package(toolsmith_package, kernel_root=kernel_root, repo_root=repo_root)
        append_package_log(kernel_root, toolsmith_package)
        package_replay_allowed, package_replay_reason = package_replay_decision(
            stage=stage,
            package=toolsmith_package,
            replay_depth=replay_depth,
        )
        if package_replay_allowed:
            replay_allowed = True
            replay_reason = package_replay_reason
            status = "promoted"
        elif toolsmith_package.status in {"generated", "verified", "promoted", "failed"}:
            status = toolsmith_package.status
        elif toolsmith_package.status == "blocked_requires_authorization":
            status = "blocked"
    effective_tool = registry_tool or gap_result.registry_tool or (toolsmith_package.registry_patch if toolsmith_package and toolsmith_package.status == "promoted" else None)
    fingerprint = ""
    if toolsmith_package:
        fingerprint = toolsmith_package.fingerprint
    else:
        tool_id = str((effective_tool or {}).get("tool_id") or "")
        entrypoint = str((effective_tool or {}).get("entrypoint") or "")
        fingerprint = repair_fingerprint(text=text, reason=reason, tool_id=tool_id, entrypoint=entrypoint)
    event = {
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "repair_fingerprint": fingerprint,
        "text": text,
        "channel": channel,
        "user_id": user_id,
        "stage": stage,
        "reason": reason,
        "execution_output_tail": execution_output[-2000:],
        "context_tail": context[-2000:],
        "gap_ref": gap_result.gap_ref,
        "gap_status": gap_result.status,
        "runner_status": status,
        "safety_class": gap_result.safety_class,
        "replay_allowed": replay_allowed,
        "replay_reason": replay_reason,
        "tool_id": (effective_tool or {}).get("tool_id"),
        "plan": asdict(gap_result.plan),
        "resolved_by": None if toolsmith_package is None else {
            "package_id": toolsmith_package.package_id,
            "status": toolsmith_package.status,
            "gap_type": toolsmith_package.gap_type,
            "tool_id": toolsmith_package.tool_id,
            "replay_policy": toolsmith_package.replay_policy,
            "verify_output_tail": toolsmith_package.verify_output[-2000:],
            "promoted_at": toolsmith_package.promoted_at,
        },
    }
    log_path = upsert_event(kernel_root, event, fingerprint)
    reply = "\n".join(
        [
            gap_result.reply,
            f"自演进状态：{status}",
            f"重放判定：{'允许' if replay_allowed else '不允许'}，{replay_reason}",
            f"工具匠：{toolsmith_package.status if toolsmith_package else 'not_needed'}",
            f"事件日志：{log_path}",
        ]
    )
    return RepairRunnerResult(
        status=status,
        stage=stage,
        safety_class=gap_result.safety_class,
        gap_ref=gap_result.gap_ref,
        replay_allowed=replay_allowed,
        replay_reason=replay_reason,
        reply=reply,
        plan=asdict(gap_result.plan),
        registry_tool=effective_tool,
        toolsmith_package=None if toolsmith_package is None else asdict(toolsmith_package),
        event_log=str(log_path),
        created_at=event["created_at"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Record and repair OpenClaw capability gaps through one bounded loop.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--channel", default="discord_dm")
    parser.add_argument("--user-id", default="unknown")
    parser.add_argument("--stage", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--execution-output", default="")
    parser.add_argument("--context", default="")
    parser.add_argument("--kernel-root", type=Path, default=DEFAULT_KERNEL_ROOT)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--replay-depth", type=int, default=0)
    args = parser.parse_args()
    result = run_repair(
        text=args.text,
        channel=args.channel,
        user_id=args.user_id,
        stage=args.stage,
        reason=args.reason,
        execution_output=args.execution_output,
        context=args.context,
        kernel_root=args.kernel_root,
        repo_root=args.repo_root,
        replay_depth=args.replay_depth,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.status in {"recorded", "planned", "generated", "verified", "promoted", "replayed", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
