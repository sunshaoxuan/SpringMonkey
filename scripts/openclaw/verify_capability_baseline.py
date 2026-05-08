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

from harness_governance import evaluate_tool_invocation
from harness_intent_agent import IntentFrame, infer_intent_frame
from harness_semantic_reviewer import review_intent_frame
from harness_tool_binder import bind_tool

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


REPO = Path(__file__).resolve().parents[2]
DEFAULT_CASES = REPO / "config" / "openclaw" / "capability_baseline_cases.json"
DEFAULT_REGISTRY = REPO / "config" / "openclaw" / "intent_tools.json"


@dataclass
class BaselineResult:
    case_id: str
    text: str
    passed: bool
    stage: str
    expected_tool_id: str
    actual_tool_id: str
    safety: str
    write_operation: bool
    reason: str
    live_intent: bool


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_text(text: str) -> str:
    return "".join((text or "").split())


def baseline_cases(path: Path = DEFAULT_CASES) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = load_json(path)
    cases = data.get("cases") if isinstance(data.get("cases"), list) else []
    return data.get("defaults") if isinstance(data.get("defaults"), dict) else {}, [case for case in cases if isinstance(case, dict)]


def find_case(text: str, cases_path: Path = DEFAULT_CASES) -> dict[str, Any] | None:
    _, cases = baseline_cases(cases_path)
    wanted = normalize_text(text)
    for case in cases:
        if normalize_text(str(case.get("text") or "")) == wanted:
            return case
    return None


def expected_signature(case: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    return {
        "domain": str(expected.get("domain") or ""),
        "action": str(expected.get("action") or ""),
        "safety": str(expected.get("safety") or ""),
        "write_operation": bool(expected.get("write_operation")),
        "tool_id": str(expected.get("tool_id") or ""),
        "capability_family": str(case.get("capability_family") or ""),
        "auto_repair": str(case.get("auto_repair") or ""),
    }


def find_capability_family_case(
    text: str,
    registry: dict[str, Any],
    cases_path: Path = DEFAULT_CASES,
    *,
    fail_open_model: bool = False,
) -> tuple[dict[str, Any] | None, IntentFrame | None, str]:
    """Find a baseline case by abstract capability shape, not exact text.

    This is intentionally conservative: the inferred frame must agree on
    domain/action/safety with an existing baseline case. It does not bind a
    specific business keyword to a repair path.
    """
    _, cases = baseline_cases(cases_path)
    try:
        frame = infer_intent_frame(text, context="", registry=registry)
    except Exception as exc:
        if fail_open_model:
            return None, None, f"intent inference unavailable: {type(exc).__name__}: {exc}"
        raise
    candidates: list[tuple[int, dict[str, Any]]] = []
    for case in cases:
        signature = expected_signature(case)
        if signature["domain"] != frame.domain or signature["action"] != frame.action:
            continue
        score = 10
        if signature["safety"] == frame.safety:
            score += 4
        elif signature["safety"] and frame.safety:
            score -= 6
        if signature["auto_repair"] == "readonly" and frame.safety == "readonly":
            score += 2
        if signature["auto_repair"] == "authorization_required" and frame.safety in {"write", "credential", "destructive"}:
            score += 2
        if signature["capability_family"]:
            score += 1
        if score > 0:
            candidates.append((score, case))
    if not candidates:
        return None, frame, f"no baseline capability family for {frame.domain}/{frame.action}/{frame.safety}"
    candidates.sort(key=lambda item: (item[0], str(item[1].get("id") or "")), reverse=True)
    return candidates[0][1], frame, "matched baseline capability family"


def make_expected_frame(case: dict[str, Any]) -> IntentFrame:
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    parameters = case.get("parameters") if isinstance(case.get("parameters"), dict) else {}
    tool_id = str(expected.get("tool_id") or "")
    return IntentFrame(
        conversation_mode="task",
        domain=str(expected.get("domain") or "unknown"),
        action=str(expected.get("action") or "gap"),
        canonical_text=str(case.get("text") or ""),
        context_refs=[],
        parameters=dict(parameters),
        safety=str(expected.get("safety") or "ambiguous"),
        result_contract={},
        tool_candidates=[{"tool_id": tool_id, "confidence": 0.99, "reason": "capability baseline expected tool"}] if tool_id else [],
        confidence=0.99,
        reason=f"capability baseline case {case.get('id')}",
        source="baseline_case",
    )


def verify_case(
    case: dict[str, Any],
    registry: dict[str, Any],
    defaults: dict[str, Any],
    *,
    live_intent: bool,
    fail_open_model: bool,
) -> BaselineResult:
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    text = str(case.get("text") or "")
    case_id = str(case.get("id") or "unknown")
    expected_tool_id = str(expected.get("tool_id") or "")
    channel = str(case.get("channel") or defaults.get("channel") or "discord_dm")
    user_id = str(case.get("user_id") or defaults.get("user_id") or "unknown")
    use_live = live_intent or bool(case.get("live_intent"))
    try:
        if use_live:
            frame = infer_intent_frame(text, context="", registry=registry)
        else:
            frame = make_expected_frame(case)
    except Exception as exc:
        if fail_open_model:
            frame = make_expected_frame(case)
            use_live = False
        else:
            return BaselineResult(case_id, text, False, "intent_frame", expected_tool_id, "", "", False, f"{type(exc).__name__}: {exc}", use_live)

    if frame.domain != str(expected.get("domain") or ""):
        return BaselineResult(case_id, text, False, "intent_frame", expected_tool_id, "", frame.safety, False, f"domain {frame.domain} != {expected.get('domain')}", use_live)
    if frame.action != str(expected.get("action") or ""):
        return BaselineResult(case_id, text, False, "intent_frame", expected_tool_id, "", frame.safety, False, f"action {frame.action} != {expected.get('action')}", use_live)
    if frame.safety != str(expected.get("safety") or ""):
        return BaselineResult(case_id, text, False, "intent_frame", expected_tool_id, "", frame.safety, False, f"safety {frame.safety} != {expected.get('safety')}", use_live)

    binding = bind_tool(frame, registry)
    actual_tool_id = str((binding.tool or {}).get("tool_id") or "")
    if binding.status != "bound" or actual_tool_id != expected_tool_id:
        return BaselineResult(case_id, text, False, "binding", expected_tool_id, actual_tool_id, frame.safety, bool((binding.tool or {}).get("write_operation")), binding.reason, use_live)

    write_operation = bool((binding.tool or {}).get("write_operation"))
    if write_operation != bool(expected.get("write_operation")):
        return BaselineResult(case_id, text, False, "binding", expected_tool_id, actual_tool_id, frame.safety, write_operation, "write_operation mismatch", use_live)

    review = review_intent_frame(frame, binding.tool, text)
    if not review.passed:
        return BaselineResult(case_id, text, False, "semantic_review", expected_tool_id, actual_tool_id, frame.safety, write_operation, review.reason, use_live)

    decision = evaluate_tool_invocation(binding.tool or {}, channel=channel, user_id=user_id)
    if decision.allowed != bool(expected.get("governance_allowed", True)):
        return BaselineResult(case_id, text, False, "governance", expected_tool_id, actual_tool_id, frame.safety, write_operation, decision.reason, use_live)

    return BaselineResult(case_id, text, True, "ok", expected_tool_id, actual_tool_id, frame.safety, write_operation, "ok", use_live)


def verify_baseline(
    *,
    cases_path: Path = DEFAULT_CASES,
    registry_path: Path = DEFAULT_REGISTRY,
    live_intent: bool = False,
    fail_open_model: bool = False,
) -> list[BaselineResult]:
    defaults, cases = baseline_cases(cases_path)
    registry = load_json(registry_path)
    return [
        verify_case(case, registry, defaults, live_intent=live_intent, fail_open_model=fail_open_model)
        for case in cases
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify stable capability baseline without executing business tools.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--live-intent", action="store_true", help="Use live intentAgent for all cases instead of case-defined expected frames.")
    parser.add_argument("--fail-open-model", action="store_true", help="Fallback to expected frames if live model is unavailable.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = verify_baseline(cases_path=args.cases, registry_path=args.registry, live_intent=args.live_intent, fail_open_model=args.fail_open_model)
    payload = {"passed": all(item.passed for item in results), "count": len(results), "results": [asdict(item) for item in results]}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"capability_baseline {'ok' if payload['passed'] else 'failed'} cases={len(results)}")
        for item in results:
            mark = "ok" if item.passed else "FAIL"
            print(f"{mark} {item.case_id} stage={item.stage} tool={item.actual_tool_id or 'none'} expected={item.expected_tool_id} reason={item.reason}")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
