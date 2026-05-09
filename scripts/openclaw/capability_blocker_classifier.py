#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from harness_intent_agent import call_model, extract_json_object, registry_prompt


BLOCKER_KINDS = {
    "access_or_approval_blocker",
    "credential_missing",
    "registered_tool_regression",
    "tool_binding_gap",
    "readonly_tool_missing",
    "write_operation_request",
    "ambiguous",
}
SAFETY_CLASSES = {
    "auto_safe_readonly",
    "requires_confirmation_or_credentials",
    "unsupported_or_ambiguous",
}
REPLAY_POLICIES = {
    "allow_after_verified_promoted",
    "blocked_until_authorization",
    "blocked_until_human_review",
}
AUTONOMOUS_REPAIR_ACTIONS = {
    "autonomous_internal_repair",
    "autonomous_readonly_repair",
    "generate_helper_and_verify",
}


@dataclass
class CapabilityBlockerClassification:
    intent_kind: str
    blocker_kind: str
    safety_class: str
    confidence: float
    expected_capability_family: str
    missing_condition: str
    allowed_repair_action: str
    replay_policy: str
    reasoning_summary: str
    autonomy_allowed: bool = False
    autonomy_boundary: str = "human_review_required"
    ok: bool = True
    error: str = ""


def conservative_blocker(error: str = "") -> CapabilityBlockerClassification:
    return CapabilityBlockerClassification(
        intent_kind="unknown",
        blocker_kind="ambiguous",
        safety_class="unsupported_or_ambiguous",
        confidence=0.0,
        expected_capability_family="unknown",
        missing_condition="model classification unavailable or low confidence",
        allowed_repair_action="record_gap_only",
        replay_policy="blocked_until_human_review",
        reasoning_summary="Conservatively blocked because the model did not produce a trusted blocker classification.",
        autonomy_allowed=False,
        autonomy_boundary="model_unavailable_or_low_confidence",
        ok=False,
        error=error,
    )


def validate_classification(data: dict[str, Any]) -> CapabilityBlockerClassification:
    blocker_kind = str(data.get("blocker_kind") or "ambiguous").strip()
    safety_class = str(data.get("safety_class") or "unsupported_or_ambiguous").strip()
    replay_policy = str(data.get("replay_policy") or "blocked_until_human_review").strip()
    if blocker_kind not in BLOCKER_KINDS:
        blocker_kind = "ambiguous"
    if safety_class not in SAFETY_CLASSES:
        safety_class = "unsupported_or_ambiguous"
    if replay_policy not in REPLAY_POLICIES:
        replay_policy = "blocked_until_human_review"
    allowed_repair_action = str(data.get("allowed_repair_action") or "record_gap_only").strip()
    autonomy_allowed = bool(data.get("autonomy_allowed")) or (
        allowed_repair_action in AUTONOMOUS_REPAIR_ACTIONS
        and safety_class == "auto_safe_readonly"
        and replay_policy == "allow_after_verified_promoted"
    )
    return CapabilityBlockerClassification(
        intent_kind=str(data.get("intent_kind") or "unknown").strip() or "unknown",
        blocker_kind=blocker_kind,
        safety_class=safety_class,
        confidence=max(0.0, min(float(data.get("confidence") or 0.0), 1.0)),
        expected_capability_family=str(data.get("expected_capability_family") or "unknown").strip() or "unknown",
        missing_condition=str(data.get("missing_condition") or "").strip(),
        allowed_repair_action=allowed_repair_action,
        replay_policy=replay_policy,
        reasoning_summary=str(data.get("reasoning_summary") or "model blocker classification").strip(),
        autonomy_allowed=autonomy_allowed,
        autonomy_boundary=str(data.get("autonomy_boundary") or ("low_risk_internal" if autonomy_allowed else "human_review_required")).strip(),
    )


def load_registry_summary(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "config" / "openclaw" / "intent_tools.json"
    if not path.is_file():
        return {"tools": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"tools": []}
    return data if isinstance(data, dict) else {"tools": []}


def build_blocker_prompt(
    *,
    text: str,
    stage: str,
    reason: str,
    execution_output: str,
    context: str,
    registry: dict[str, Any],
) -> list[dict[str, str]]:
    system = (
        "You are OpenClaw's semantic capability-blocker classifier. "
        "Return strict JSON only. "
        "Schema: {intent_kind, blocker_kind, safety_class, confidence, expected_capability_family, "
        "missing_condition, allowed_repair_action, replay_policy, reasoning_summary, autonomy_allowed, autonomy_boundary}. "
        "blocker_kind must be one of: access_or_approval_blocker, credential_missing, "
        "registered_tool_regression, tool_binding_gap, readonly_tool_missing, write_operation_request, ambiguous. "
        "safety_class must be one of: auto_safe_readonly, requires_confirmation_or_credentials, unsupported_or_ambiguous. "
        "replay_policy must be one of: allow_after_verified_promoted, blocked_until_authorization, blocked_until_human_review. "
        "Classify by semantic meaning, not by keyword matching. "
        "Default autonomy policy: allow the agent to operate freely for low-risk self-improvement, internal logs, repository changes, helper generation, tests, "
        "registry updates, local/remote verification, and retrying the original task when no personal privacy is exposed and no third-party rights are affected. "
        "For those low-risk internal repairs, set autonomy_allowed=true, safety_class=auto_safe_readonly, "
        "allowed_repair_action=autonomous_internal_repair, replay_policy=allow_after_verified_promoted. "
        "Do not block merely because the text mentions access or approval if the missing access can be resolved with already authorized internal tools, "
        "owner-owned workspace state, generated artifacts, or existing service credentials. "
        "Choose access_or_approval_blocker with requires_confirmation_or_credentials and blocked_until_authorization only when external approval is actually missing, "
        "the agent would need to bypass access control, expose private data outside the owner boundary, or affect another person's rights. "
        "If credentials, login, 2FA, token, or secret material is missing, choose credential_missing. "
        "If the request is a known existing capability that should have bound to a registered tool, choose registered_tool_regression. "
        "If the user asks for a safe read-only capability that needs a new deterministic helper, choose readonly_tool_missing. "
        "If the request changes external state or writes data outside the self-improvement workspace, choose write_operation_request. "
        "If uncertain, choose ambiguous and blocked_until_human_review. "
        "Never suggest generating a helper for credential theft, access-control bypass, privacy exposure, payment, deletion, or third-party-rights-impacting actions."
    )
    user = "\n".join(
        [
            "Registered tool capabilities:",
            registry_prompt(registry),
            "Original user text:",
            text,
            "Failure stage:",
            stage,
            "Failure reason:",
            reason,
            "Execution output:",
            execution_output[-3000:] or "(none)",
            "Context:",
            context[-3000:] or "(none)",
        ]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def classify_capability_blocker(
    *,
    text: str,
    stage: str,
    reason: str,
    execution_output: str = "",
    context: str = "",
    repo_root: Path | None = None,
    registry: dict[str, Any] | None = None,
    model_caller: Callable[[list[dict[str, str]]], str] | None = None,
    timeout: int = 20,
    min_confidence: float = 0.7,
) -> CapabilityBlockerClassification:
    repo_root = repo_root or Path(__file__).resolve().parents[2]
    registry = registry or load_registry_summary(repo_root)
    messages = build_blocker_prompt(
        text=text,
        stage=stage,
        reason=reason,
        execution_output=execution_output,
        context=context,
        registry=registry,
    )
    try:
        if model_caller is not None:
            content = model_caller(messages)
        else:
            content, _meta = call_model(messages, timeout=timeout, temperature=0)
        classification = validate_classification(extract_json_object(content))
    except Exception as exc:
        return conservative_blocker(f"{type(exc).__name__}: {exc}")
    if classification.confidence < min_confidence:
        blocked = conservative_blocker(f"low confidence: {classification.confidence}")
        blocked.intent_kind = classification.intent_kind
        blocked.expected_capability_family = classification.expected_capability_family
        blocked.reasoning_summary = classification.reasoning_summary
        return blocked
    return classification


def classification_dict(classification: CapabilityBlockerClassification | None) -> dict[str, Any] | None:
    return None if classification is None else asdict(classification)
