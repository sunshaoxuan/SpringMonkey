from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness_dispatcher import handle_event
from harness_governance import evaluate_tool_invocation
from harness_reporter import ReportEnvelope, append_report, format_owner_reply


def test_dispatcher_builds_context_before_intent_model() -> None:
    seen: dict[str, str] = {}

    def model_caller(messages: list[dict[str, str]]) -> str:
        seen["prompt"] = messages[-1]["content"]
        return json.dumps(
            {
                "conversation_mode": "chat",
                "domain": "general",
                "action": "chat",
                "canonical_text": "我在。",
                "context_refs": [],
                "parameters": {},
                "safety": "readonly",
                "result_contract": {},
                "tool_candidates": [],
                "confidence": 0.99,
                "reason": "chat",
            },
            ensure_ascii=False,
        )

    with tempfile.TemporaryDirectory() as tmp:
        result = handle_event(
            text="还活着吗",
            channel="discord_dm",
            user_id="999666719356354610",
            message_timestamp="2026-05-05T00:00:00+09:00",
            registry={"tools": []},
            context="Referenced message: previous tool result",
            kernel_root=Path(tmp) / "kernel",
            timeout_seconds=10,
            extract_args=lambda _tool, _text, _ts: {},
            run_tool=lambda _tool, _args, _timeout: (0, ""),
            format_reply=lambda _tool, _args, _code, output: output,
            audit_intent=lambda **_kwargs: None,
            evaluate_result=lambda _tool, _output, _contract: None,
            model_caller=model_caller,
        )
    assert result.status == "chat"
    assert result.context_summary and result.context_summary["dm_context"] is True
    assert "DM context:" in seen["prompt"]
    assert "Referenced message: previous tool result" in seen["prompt"]
    assert "Registry summary:" in seen["prompt"]


def test_governance_public_write_denial_sets_owner_dm_visibility() -> None:
    tool = {
        "tool_id": "timescar.dm.cancel_next",
        "permission": "owner_dm_write",
        "write_operation": True,
        "confirm_policy": "confirm",
        "idempotency": "postcheck",
    }
    decision = evaluate_tool_invocation(tool, channel="discord_public", user_id="999666719356354610")
    assert not decision.allowed
    assert decision.report_visibility == "owner_dm"
    assert "write_operation_requires_owner_dm" in decision.policy_hits


def test_reporter_formats_trace_stage_tool_and_postcheck() -> None:
    envelope = ReportEnvelope(
        task_id="task_test",
        trace_id="trace_test",
        status="failed",
        visibility="owner_dm",
        summary="TimesCar 写操作未报成功。",
        diagnostics_ref="trace_id=trace_test route=result_contract_failed",
        stage="evaluate",
        tool_id="timescar.dm.cancel_next",
        worker_agent="timescarWorker",
        write_operation=True,
        postcheck="target_booking_absent_after_success",
        failure_type="result_contract_failed",
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = append_report(envelope, path=Path(tmp) / "reports.jsonl")
        saved = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    reply = format_owner_reply(envelope)
    assert saved["trace_id"] == "trace_test"
    assert "阶段：evaluate" in reply
    assert "工具：timescar.dm.cancel_next" in reply
    assert "回查：target_booking_absent_after_success" in reply


def test_discord_patch_does_not_add_business_router_success_prefix() -> None:
    source = (Path(__file__).resolve().parent / "patch_discord_timescar_dm_preroute.py").read_text(encoding="utf-8")
    assert "汤猴私信任务已由通用事件路由处理。" not in source
    assert "汤猴私信任务路由失败" in source
