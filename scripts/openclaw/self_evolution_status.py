#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_KERNEL_ROOT = Path("/var/lib/openclaw/.openclaw/workspace/agent_society_kernel")


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
        if status == "awaiting_authorization":
            return "regression_detected -> package_verified -> awaiting_authorization"
        if status in {"verified", "deployed"}:
            return f"regression_detected -> package_{status} -> replay_ready"
        return f"regression_detected -> {status}"
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Report current Agent Society self-evolution status.")
    parser.add_argument("--kernel-root", type=Path, default=DEFAULT_KERNEL_ROOT)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    events = read_jsonl_tail(args.kernel_root / "capability_gap_events.jsonl", args.limit)
    regressions = read_jsonl_tail(args.kernel_root / "regression_repair_packages.jsonl", args.limit)
    plans = read_jsonl_tail(args.kernel_root / "dm_capability_plans.jsonl", args.limit)
    registry = args.kernel_root / "helper_registry.json"
    helper_count = 0
    if registry.is_file():
        try:
            helper_count = len(json.loads(registry.read_text(encoding="utf-8")).get("promoted_helpers", []))
        except Exception:
            helper_count = 0
    lines = [
        "自演进状态",
        f"能力缺口事件：{len(events)} 条最近记录",
        f"补强计划：{len(plans)} 条最近记录",
        f"回归收紧包：{len(regressions)} 条最近记录",
        f"已推广 helper：{helper_count}",
    ]
    unresolved = [
        event
        for event in events
        if str(event.get("runner_status") or "") not in {"promoted", "verified", "deployed", "replayed"}
        and not bool(event.get("replay_allowed"))
    ]
    if unresolved:
        lines.append(f"未解决缺口：{len(unresolved)}")
    for index, event in enumerate(reversed(events), start=1):
        resolved_by = event.get("resolved_by") if isinstance(event.get("resolved_by"), dict) else {}
        lines.append(
            f"{index}. stage={event.get('stage')} status={event.get('runner_status')} "
            f"safety={event.get('safety_class')} replay={event.get('replay_allowed')} "
            f"tool={event.get('tool_id') or 'none'} lifecycle={lifecycle(event)} "
            f"baseline={event.get('baseline_case_id') or 'none'} "
            f"regression={event.get('regression_type') or 'none'} "
            f"resolved_by={resolved_by.get('package_id') or 'none'} "
            f"fingerprint={event.get('repair_fingerprint') or 'none'} "
            f"verify={str(resolved_by.get('verify_output_tail') or '')[:120]}"
        )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
