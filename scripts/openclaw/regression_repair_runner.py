#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from verify_capability_baseline import DEFAULT_CASES, DEFAULT_REGISTRY, find_case, load_json, verify_case

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


DEFAULT_KERNEL_ROOT = Path("/var/lib/openclaw/.openclaw/workspace/agent_society_kernel")


@dataclass
class RegressionRepair:
    matched: bool
    status: str
    regression_type: str
    baseline_case_id: str
    expected_tool_id: str
    actual_stage: str
    write_operation: bool
    auto_repair: str
    fingerprint: str
    package: dict[str, Any]
    log_path: str
    reason: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def regression_fingerprint(case_id: str, text: str, stage: str, reason: str, expected_tool_id: str) -> str:
    payload = json.dumps(
        {
            "case_id": case_id,
            "text": " ".join((text or "").split())[:500],
            "stage": stage,
            "reason": " ".join((reason or "").split())[:500],
            "expected_tool_id": expected_tool_id,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def classify_regression(stage: str, reason: str, baseline_passed: bool, actual_tool_id: str, expected_tool_id: str) -> str:
    lowered = (reason or "").lower()
    if stage == "binding" or "no registered tool" in lowered or not actual_tool_id:
        return "existing_tool_regression" if expected_tool_id else "registry_pattern_gap"
    if stage == "intent" or "intent" in lowered or actual_tool_id != expected_tool_id:
        return "intent_frame_gap"
    if stage == "semantic_review":
        return "semantic_review_overblock"
    if stage == "governance":
        return "governance_policy_mismatch"
    if stage in {"execute", "evaluate"}:
        return "executor_parser_gap"
    if not baseline_passed:
        return "existing_tool_regression"
    return "existing_tool_regression"


def package_status(write_operation: bool, baseline_passed: bool) -> str:
    if write_operation:
        return "awaiting_authorization"
    return "verified" if baseline_passed else "generated"


def build_package(
    *,
    case: dict[str, Any],
    stage: str,
    reason: str,
    regression_type: str,
    baseline_result: Any,
    fingerprint: str,
) -> dict[str, Any]:
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    write_operation = bool(expected.get("write_operation"))
    status = package_status(write_operation, bool(getattr(baseline_result, "passed", False)))
    verify_command = (
        "python scripts/openclaw/verify_capability_baseline.py && "
        "python -m pytest -q scripts/openclaw/test_capability_baseline.py scripts/openclaw/test_regression_repair_runner.py"
    )
    return {
        "package_id": f"regression_{fingerprint}",
        "status": status,
        "regression_type": regression_type,
        "baseline_case_id": case.get("id"),
        "text": case.get("text"),
        "expected_tool_id": expected.get("tool_id"),
        "actual_stage": stage,
        "reason": reason,
        "write_operation": write_operation,
        "auto_repair": case.get("auto_repair") or ("authorization_required" if write_operation else "readonly"),
        "candidate_changes": [
            "tighten intent routing or registry patterns for the baseline case",
            "add or update a regression test that uses the baseline text",
            "run capability baseline before deployment",
        ],
        "minimal_test": f"baseline case {case.get('id')} must bind to {expected.get('tool_id')}",
        "verify_command": verify_command,
        "deployment_policy": "await_explicit_authorization" if write_operation else "auto_deploy_after_verify",
        "baseline_result": asdict(baseline_result),
        "created_at": utc_now(),
    }


def append_regression_log(kernel_root: Path, package: dict[str, Any], fingerprint: str) -> Path:
    path = kernel_root / "regression_repair_packages.jsonl"
    rows: list[dict[str, Any]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    replaced = False
    for index, row in enumerate(rows):
        if row.get("fingerprint") == fingerprint:
            rows[index] = package
            replaced = True
            break
    if not replaced:
        rows.append(package)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    return path


def run_regression_repair(
    *,
    text: str,
    stage: str,
    reason: str,
    kernel_root: Path = DEFAULT_KERNEL_ROOT,
    cases_path: Path = DEFAULT_CASES,
    registry_path: Path = DEFAULT_REGISTRY,
) -> RegressionRepair:
    if not cases_path.is_file() or not registry_path.is_file():
        return RegressionRepair(False, "not_baseline_gap", "", "", "", stage, False, "", "", {}, "", "baseline registry is not available")
    case = find_case(text, cases_path)
    if not case:
        return RegressionRepair(False, "not_baseline_gap", "", "", "", stage, False, "", "", {}, "", "no matching baseline case")
    data = load_json(cases_path)
    defaults = data.get("defaults") if isinstance(data.get("defaults"), dict) else {}
    registry = load_json(registry_path)
    baseline = verify_case(case, registry, defaults, live_intent=bool(case.get("live_intent")), fail_open_model=False)
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    expected_tool_id = str(expected.get("tool_id") or "")
    regression_type = classify_regression(stage, reason, baseline.passed, baseline.actual_tool_id, expected_tool_id)
    fingerprint = regression_fingerprint(str(case.get("id") or ""), text, stage, reason, expected_tool_id)
    package = build_package(
        case=case,
        stage=stage,
        reason=reason,
        regression_type=regression_type,
        baseline_result=baseline,
        fingerprint=fingerprint,
    )
    package["fingerprint"] = fingerprint
    log_path = append_regression_log(kernel_root, package, fingerprint)
    return RegressionRepair(
        True,
        str(package["status"]),
        regression_type,
        str(case.get("id") or ""),
        expected_tool_id,
        stage,
        bool(expected.get("write_operation")),
        str(package["auto_repair"]),
        fingerprint,
        package,
        str(log_path),
        "matched existing capability baseline",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a structured repair package for baseline capability regressions.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--kernel-root", type=Path, default=DEFAULT_KERNEL_ROOT)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    args = parser.parse_args()
    result = run_regression_repair(
        text=args.text,
        stage=args.stage,
        reason=args.reason,
        kernel_root=args.kernel_root,
        cases_path=args.cases,
        registry_path=args.registry,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
