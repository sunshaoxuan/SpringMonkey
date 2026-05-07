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


def main() -> int:
    parser = argparse.ArgumentParser(description="Report current Agent Society self-evolution status.")
    parser.add_argument("--kernel-root", type=Path, default=DEFAULT_KERNEL_ROOT)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    events = read_jsonl_tail(args.kernel_root / "capability_gap_events.jsonl", args.limit)
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
        f"已推广 helper：{helper_count}",
    ]
    for index, event in enumerate(reversed(events), start=1):
        lines.append(
            f"{index}. stage={event.get('stage')} status={event.get('runner_status')} "
            f"safety={event.get('safety_class')} replay={event.get('replay_allowed')} "
            f"tool={event.get('tool_id') or 'none'}"
        )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
