#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


DEFAULT_KERNEL_ROOT = Path("/var/lib/openclaw/.openclaw/workspace/agent_society_kernel")
DEFAULT_LONG_TASK_STATE = Path("/var/lib/openclaw/.openclaw/workspace/state/long_task_supervisor/tasks.json")

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def read_jsonl_tail(path: Path, limit: int) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def lifecycle(event: dict) -> str:
    status = str(event.get("runner_status") or "recorded")
    if event.get("regression_ref"):
        if event.get("match_kind") == "capability_family":
            if status == "awaiting_authorization":
                return "known_direction_detected -> package_verified -> awaiting_authorization"
            if status in {"verified", "deployed"}:
                return f"known_direction_detected -> package_{status} -> replay_ready"
            return f"known_direction_detected -> {status}"
        if status == "awaiting_authorization":
            return "regression_detected -> package_verified -> awaiting_authorization"
        if status in {"verified", "deployed"}:
            return f"regression_detected -> package_{status} -> replay_ready"
        return f"regression_detected -> {status}"
    if event.get("autonomy_allowed"):
        if status == "repair_started":
            return "recorded -> llm_autonomy_allowed -> package_planned -> implementation_started"
        return f"recorded -> llm_autonomy_allowed -> {status}"
    if event.get("llm_blocker_kind") in {"access_or_approval_blocker", "credential_missing"}:
        return "recorded -> llm_blocker_classified -> awaiting_authorization"
    if event.get("replay_allowed"):
        if status == "deployed":
            return "recorded -> planned -> generated -> verified -> promoted -> deployed -> replay_ready"
        if status == "promoted":
            return "recorded -> planned -> generated -> verified -> promoted -> replay_ready"
        return "recorded -> planned -> verified -> replay_ready"
    resolved_by = event.get("resolved_by") if isinstance(event.get("resolved_by"), dict) else {}
    package_status = str(resolved_by.get("status") or "")
    if package_status == "generated":
        return "recorded -> planned -> generated -> verify_required"
    if package_status == "verified":
        return "recorded -> planned -> generated -> verified -> promote_required"
    if package_status == "promoted":
        return "recorded -> planned -> generated -> verified -> promoted"
    if package_status == "deployed":
        return "recorded -> planned -> generated -> verified -> promoted -> deployed"
    if package_status == "failed":
        return "recorded -> planned -> generated -> failed"
    if package_status == "blocked_requires_authorization" or status == "blocked":
        return "recorded -> planned -> blocked"
    return f"recorded -> {status}"


def package_state(kernel_root: Path, package_id: str) -> dict:
    if not package_id:
        return {}
    state_path = kernel_root / "toolsmith_packages" / package_id / "package_state.json"
    if not state_path.is_file():
        return {}
    try:
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def effective_event(kernel_root: Path, event: dict) -> dict:
    resolved_by = event.get("resolved_by") if isinstance(event.get("resolved_by"), dict) else {}
    state = package_state(kernel_root, str(resolved_by.get("package_id") or ""))
    state_status = str(state.get("status") or "")
    if state_status != "superseded":
        return event
    updated = dict(event)
    updated["runner_status"] = "superseded"
    updated["replay_allowed"] = False
    updated_resolved = dict(resolved_by)
    updated_resolved["status"] = "superseded"
    updated_resolved["deployment_status"] = str(state.get("deployment_status") or "superseded")
    updated["resolved_by"] = updated_resolved
    return updated


def helper_count_from_registry(registry_path: Path) -> int:
    if not registry_path.is_file():
        return 0
    try:
        loaded = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if isinstance(loaded, dict):
        helpers = loaded.get("promoted_helpers")
        if isinstance(helpers, list):
            return len(helpers)
        return len(loaded)
    if isinstance(loaded, list):
        return len(loaded)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Report current Agent Society self-evolution status.")
    parser.add_argument("--kernel-root", type=Path, default=DEFAULT_KERNEL_ROOT)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    events = [effective_event(args.kernel_root, event) for event in read_jsonl_tail(args.kernel_root / "capability_gap_events.jsonl", args.limit)]
    display_events = [event for event in events if str(event.get("runner_status") or "") != "superseded"]
    regressions = read_jsonl_tail(args.kernel_root / "regression_repair_packages.jsonl", args.limit)
    plans = read_jsonl_tail(args.kernel_root / "dm_capability_plans.jsonl", args.limit)
    registry = args.kernel_root / "helper_registry.json"
    helper_count = helper_count_from_registry(registry)
    long_tasks: list[dict] = []
    if DEFAULT_LONG_TASK_STATE.is_file():
        try:
            loaded = json.loads(DEFAULT_LONG_TASK_STATE.read_text(encoding="utf-8"))
            long_tasks = [item for item in loaded.get("tasks", []) if isinstance(item, dict)][-args.limit :]
        except Exception:
            long_tasks = []
    lines = [
        "自演进状态",
        f"能力缺口事件：{len(display_events)} 条最近有效记录",
        f"补强计划：{len(plans)} 条最近记录",
        f"回归收紧包：{len(regressions)} 条最近记录",
        f"已推广 helper：{helper_count}",
        f"长任务记录：{len(long_tasks)} 条最近记录",
    ]
    active_long_tasks = [item for item in long_tasks if str(item.get("status") or "") in {"running", "final_detected", "delivery_failed"}]
    if active_long_tasks:
        lines.append(f"长任务待收口：{len(active_long_tasks)}")
    unresolved = [
        event
        for event in display_events
        if str(event.get("runner_status") or "") not in {"promoted", "verified", "deployed", "replayed", "superseded"}
        and not bool(event.get("replay_allowed"))
    ]
    if unresolved:
        lines.append(f"未解决缺口：{len(unresolved)}")
    for index, task in enumerate(reversed(long_tasks), start=1):
        title = str(task.get("job_name") or task.get("job_id") or task.get("run_id") or "long task")
        lines.append(
            f"long-task {index}. {title} status={task.get('status')} "
            f"stage={task.get('stage')} delivery={task.get('delivery_state')}"
        )
    for index, event in enumerate(reversed(display_events), start=1):
        resolved_by = event.get("resolved_by") if isinstance(event.get("resolved_by"), dict) else {}
        lines.append(
            f"{index}. stage={event.get('stage')} status={event.get('runner_status')} "
            f"safety={event.get('safety_class')} replay={event.get('replay_allowed')} "
            f"tool={event.get('tool_id') or 'none'} lifecycle={lifecycle(event)} "
            f"baseline={event.get('baseline_case_id') or 'none'} "
            f"regression={event.get('regression_type') or 'none'} "
            f"llm_blocker={event.get('llm_blocker_kind') or 'none'} "
            f"autonomy={event.get('autonomy_allowed') if event.get('autonomy_allowed') is not None else 'none'} "
            f"match={event.get('match_kind') or 'none'} "
            f"resolved_by={resolved_by.get('package_id') or 'none'} "
            f"implementation={((resolved_by.get('implementation_run') or {}) if isinstance(resolved_by.get('implementation_run'), dict) else {}).get('run_id') or 'none'} "
            f"fingerprint={event.get('repair_fingerprint') or 'none'} "
            f"verify={str(resolved_by.get('verify_output_tail') or '')[:120]}"
        )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
