from __future__ import annotations

import json
from pathlib import Path

import capability_blocker_classifier as classifier


def test_llm_blocker_classifier_accepts_access_approval_structure() -> None:
    payload = {
        "intent_kind": "task",
        "blocker_kind": "access_or_approval_blocker",
        "safety_class": "requires_confirmation_or_credentials",
        "confidence": 0.91,
        "expected_capability_family": "document_access",
        "missing_condition": "external approval is required before the user can inspect the artifact",
        "allowed_repair_action": "record authorization requirement and retry after access is granted",
        "replay_policy": "blocked_until_authorization",
        "reasoning_summary": "The user is describing an access blocker, not asking for a read-only helper.",
    }
    result = classifier.classify_capability_blocker(
        text="我看不到，需要批准后才能继续",
        stage="binding",
        reason="no registered tool",
        repo_root=Path(__file__).resolve().parents[2],
        registry={"tools": []},
        model_caller=lambda _messages: json.dumps(payload, ensure_ascii=False),
    )

    assert result.ok is True
    assert result.blocker_kind == "access_or_approval_blocker"
    assert result.safety_class == "requires_confirmation_or_credentials"
    assert result.replay_policy == "blocked_until_authorization"


def test_llm_blocker_classifier_low_confidence_is_conservative() -> None:
    result = classifier.classify_capability_blocker(
        text="处理一下",
        stage="binding",
        reason="unclear",
        repo_root=Path(__file__).resolve().parents[2],
        registry={"tools": []},
        model_caller=lambda _messages: json.dumps(
            {
                "intent_kind": "task",
                "blocker_kind": "readonly_tool_missing",
                "safety_class": "auto_safe_readonly",
                "confidence": 0.2,
                "expected_capability_family": "unknown",
                "missing_condition": "",
                "allowed_repair_action": "generate_helper",
                "replay_policy": "allow_after_verified_promoted",
                "reasoning_summary": "low confidence",
            }
        ),
    )

    assert result.ok is False
    assert result.blocker_kind == "ambiguous"
    assert result.safety_class == "unsupported_or_ambiguous"
    assert result.replay_policy == "blocked_until_human_review"
