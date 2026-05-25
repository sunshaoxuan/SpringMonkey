from __future__ import annotations

import llm_repair_advisor as advisor


def test_repair_advisor_parses_strict_json_response() -> None:
    def fake_model(messages, **kwargs):
        return (
            '{"failure_class":"verify_failed","root_cause":"missing test",'
            '"next_actions":["add test","run pytest"],'
            '"verification_plan":["python -m pytest -q scripts/openclaw"],'
            '"replay_policy":"replay_after_verified_commit"}',
            {"provider": "openai_compatible", "model": "gpt-5.5", "fallback_used": False},
        )

    result = advisor.get_repair_advice(
        task_text="fix self evolution",
        failure_stage="verify_failed",
        failure_reason="pytest failed",
        model_caller=fake_model,
    )

    assert result.status == "ok"
    assert result.model == "gpt-5.5"
    assert result.failure_class == "verify_failed"
    assert result.next_actions == ["add test", "run pytest"]
    assert result.replay_policy == "replay_after_verified_commit"


def test_repair_advisor_failure_is_structured() -> None:
    def fake_model(messages, **kwargs):
        raise RuntimeError("model down")

    result = advisor.get_repair_advice(
        task_text="fix self evolution",
        failure_stage="failed",
        failure_reason="no output",
        model_caller=fake_model,
    )

    assert result.status == "failed"
    assert result.failure_class == "advisor_failed"
    assert "model down" in result.error


def test_format_advice_for_report_is_short_and_actionable() -> None:
    result = advisor.RepairAdvice(
        status="ok",
        provider="openai_compatible",
        model="gpt-5.5",
        fallback_used=False,
        failure_class="route_gap",
        root_cause="tool binding did not continue after repair_started",
        next_actions=["wire advisor to supervisor"],
        verification_plan=["python scripts/openclaw/verify_capability_baseline.py"],
        replay_policy="replay_after_verified_commit",
        raw_response="{}",
    )

    text = advisor.format_advice_for_report(result)

    assert "模型修复建议" in text
    assert "route_gap" in text
    assert "wire advisor" in text
