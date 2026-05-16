#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from verify_capability_baseline import DEFAULT_CASES, DEFAULT_REGISTRY, verify_baseline


WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")
DEFAULT_TRIAL_LOG = WORKSPACE / "var" / "harness_trials.jsonl"


@dataclass
class EvalSuiteResult:
    passed: bool
    baseline_passed: bool
    baseline_count: int
    trial_count: int
    bad_trials: list[dict[str, Any]]
    outcome_summary: dict[str, int]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def summarize_trials(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    summary: dict[str, int] = {}
    bad: list[dict[str, Any]] = []
    for row in rows:
        outcome = str(row.get("outcome") or "unknown")
        summary[outcome] = summary.get(outcome, 0) + 1
        status = str(row.get("status") or "")
        stage = str(row.get("stage") or "")
        if status == "ok" and outcome != "completed":
            bad.append({"trace_id": row.get("trace_id"), "reason": "ok status without completed outcome", "stage": stage})
        if status in {"failed", "unsupported"} and not str(row.get("failure_type") or ""):
            bad.append({"trace_id": row.get("trace_id"), "reason": "failed/unsupported trial missing failure_type", "stage": stage})
    return bad, summary


def run_eval_suite(
    *,
    cases_path: Path = DEFAULT_CASES,
    registry_path: Path = DEFAULT_REGISTRY,
    trial_log: Path = DEFAULT_TRIAL_LOG,
    require_trials: bool = False,
) -> EvalSuiteResult:
    baseline = verify_baseline(cases_path=cases_path, registry_path=registry_path)
    trials = read_jsonl(trial_log)
    bad_trials, outcome_summary = summarize_trials(trials)
    baseline_passed = all(item.passed for item in baseline)
    passed = baseline_passed and not bad_trials and (bool(trials) or not require_trials)
    return EvalSuiteResult(
        passed=passed,
        baseline_passed=baseline_passed,
        baseline_count=len(baseline),
        trial_count=len(trials),
        bad_trials=bad_trials,
        outcome_summary=outcome_summary,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Harness baseline plus transcript/outcome trial records.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--trial-log", type=Path, default=DEFAULT_TRIAL_LOG)
    parser.add_argument("--require-trials", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_eval_suite(cases_path=args.cases, registry_path=args.registry, trial_log=args.trial_log, require_trials=args.require_trials)
    payload = asdict(result)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"harness_eval {'ok' if result.passed else 'failed'} baseline={result.baseline_count} trials={result.trial_count}")
        for bad in result.bad_trials[:10]:
            print(f"FAIL trace={bad.get('trace_id') or 'unknown'} stage={bad.get('stage') or 'unknown'} reason={bad.get('reason')}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
