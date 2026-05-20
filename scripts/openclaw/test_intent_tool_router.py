from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import intent_tool_router as router
import harness_dispatcher
import harness_intent_audit
import harness_intent_completion
import nl_time_range
from dm_capability_gap_runner import CapabilityPlan, GapRunnerResult
from harness_intent_agent import IntentFrame, infer_intent_frame


os.environ.setdefault("OPENCLAW_ENABLE_LEGACY_PATTERN_CLASSIFY", "1")


def load_registry() -> dict:
    return router.load_registry()


def test_legacy_pattern_classifier_is_disabled_by_default() -> None:
    with patch.dict(os.environ, {}, clear=True):
        result = router.classify("请查询明天东京天气", "discord_dm", "999", load_registry())
    assert result.tool_id is None
    assert "disabled by default" in result.reason


def registry_tool(tool_id: str) -> dict:
    registry = load_registry()
    return next(tool for tool in registry["tools"] if tool["tool_id"] == tool_id)


def intent_frame(
    *,
    mode: str = "task",
    domain: str = "timescar",
    action: str = "query",
    canonical_text: str = "查询 TimesCar 预约 未来一个月",
    safety: str = "readonly",
    tool_id: str | None = "timescar.dm.query",
    parameters: dict | None = None,
) -> IntentFrame:
    return IntentFrame(
        conversation_mode=mode,
        domain=domain,
        action=action,
        canonical_text=canonical_text,
        context_refs=[],
        parameters=parameters or {"duration_hours": 720, "offset_hours": 0, "relation": "within"},
        safety=safety,
        result_contract={},
        tool_candidates=[{"tool_id": tool_id, "confidence": 0.95, "reason": "test"}] if tool_id else [],
        confidence=0.95,
        reason="test frame",
    )


def test_timescar_query_classifies_to_registered_tool() -> None:
    result = router.classify("汤猴，检查一下未来48小时的订车记录。", "discord_dm", "999", load_registry())
    assert result.intent_id == "timescar.reservation_query"
    assert result.tool_id == "timescar.dm.query"


def test_timescar_query_week_audit_contract() -> None:
    registry = load_registry()
    tool = next(item for item in registry["tools"] if item["tool_id"] == "timescar.dm.query")
    args = router.extract_args(tool, "查一下未来一周的订车记录", "2026-05-04T00:00:00+09:00")
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        router.os.environ,
        {"OPENCLAW_HARNESS_INTENT_AUDIT_LOG": str(Path(tmp) / "audit.jsonl")},
    ):
        audit = router.audit_intent(text=args["text"], context="", selected_tool=tool, extracted_args=args)
    assert audit.result_contract["requested_hours"] == 24 * 7
    assert audit.corrected_args["_requested_range_hours"] == 24 * 7


def test_natural_language_time_range_parameter_parser() -> None:
    assert nl_time_range.requested_range_hours("查一下未来2周的订车记录") == 24 * 14
    assert nl_time_range.requested_range_hours("查一下未来两周的订车记录") == 24 * 14
    assert nl_time_range.requested_range_hours("未来三週間の予約") == 24 * 21
    assert nl_time_range.requested_range_hours("未来10天的预约") == 24 * 10
    assert nl_time_range.requested_range_hours("未来十二小时的预约") == 12
    assert nl_time_range.requested_range_hours("未来４８小時の予約") == 48
    assert nl_time_range.requested_range_hours("一个月的") == 24 * 30
    assert nl_time_range.requested_range_hours("未来1ヶ月の予約") == 24 * 30
    after = nl_time_range.requested_range_spec("未来一个月以后")
    assert after
    assert after.duration_hours == 24 * 30
    assert after.offset_hours == 24 * 30
    assert after.relation == "after"


def test_implicit_range_followup_inherits_recent_timescar_query_and_enriches_text() -> None:
    registry = load_registry()
    tool = next(item for item in registry["tools"] if item["tool_id"] == "timescar.dm.query")
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "invocations.jsonl"
        log.write_text(json.dumps({"tool_id": "timescar.dm.query", "trace_id": "trace_old"}, ensure_ascii=False) + "\n", encoding="utf-8")
        with patch.dict(harness_intent_audit.os.environ, {"OPENCLAW_HARNESS_TOOL_INVOCATION_LOG": str(log)}):
            assert harness_intent_audit.resolve_correction_tool_id("一个月的") == "timescar.dm.query"
        args = router.extract_args(tool, "一个月的", "2026-05-04T00:00:00+09:00")
        with patch.dict(router.os.environ, {"OPENCLAW_HARNESS_INTENT_AUDIT_LOG": str(Path(tmp) / "audit.jsonl")}):
            audit = router.audit_intent(text=args["text"], context="", selected_tool=tool, extracted_args=args)
    assert audit.result_contract["requested_hours"] == 24 * 30
    assert audit.result_contract["offset_hours"] == 0
    assert audit.corrected_args["_intent_audit_implied_query"] is True
    assert "TimesCar" in audit.corrected_args["text"]


def test_after_suffix_creates_offset_range_contract() -> None:
    registry = load_registry()
    tool = next(item for item in registry["tools"] if item["tool_id"] == "timescar.dm.query")
    args = router.extract_args(tool, "未来一个月以后的呢？", "2026-05-05T20:50:00+09:00")
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        router.os.environ,
        {"OPENCLAW_HARNESS_INTENT_AUDIT_LOG": str(Path(tmp) / "audit.jsonl")},
    ):
        audit = router.audit_intent(text=args["text"], context="TimesCar query", selected_tool=tool, extracted_args=args)
    assert audit.result_contract["requested_hours"] == 24 * 30
    assert audit.result_contract["offset_hours"] == 24 * 30
    assert audit.result_contract["relation"] == "after"
    assert audit.result_contract["expected_range_start"].startswith("2026-06-04T20:50")


def test_model_intent_frame_overrides_parameter_semantics() -> None:
    registry = load_registry()
    tool = next(item for item in registry["tools"] if item["tool_id"] == "timescar.dm.query")
    classification = router.Classification(
        "timescar.reservation_query",
        "timescar.dm.query",
        0.98,
        "model semantic frame",
        tool,
        {
            "source": "model",
            "tool_id": "timescar.dm.query",
            "canonical_text": "查询 TimesCar 预约 未来一个月以后",
            "parameters": {"duration_hours": 720, "offset_hours": 720, "relation": "after"},
        },
    )
    args = router.extract_args(tool, "未来一个月以后", "2026-05-05T20:50:00+09:00")
    args = router.apply_model_intent_frame(args, classification)
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        router.os.environ,
        {"OPENCLAW_HARNESS_INTENT_AUDIT_LOG": str(Path(tmp) / "audit.jsonl")},
    ):
        audit = router.audit_intent(text=args["text"], context="", selected_tool=tool, extracted_args=args)
    assert audit.corrected_args["text"] == "查询 TimesCar 预约 未来一个月以后"
    assert audit.corrected_args["_intent_audit_model_frame_used"] is True
    assert audit.result_contract["offset_hours"] == 720
    assert audit.result_contract["relation"] == "after"


def test_intent_completion_records_inherited_query_and_parameter_override() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        invocation_log = Path(tmp) / "invocations.jsonl"
        completion_log = Path(tmp) / "completions.jsonl"
        invocation_log.write_text(
            json.dumps(
                {
                    "tool_id": "timescar.dm.query",
                    "trace_id": "trace_old",
                    "task_id": "task_old",
                    "input_summary": "查一下未来一周的订车记录",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        with patch.dict(
            harness_intent_completion.os.environ,
            {
                "OPENCLAW_HARNESS_TOOL_INVOCATION_LOG": str(invocation_log),
                "OPENCLAW_HARNESS_INTENT_COMPLETION_LOG": str(completion_log),
            },
        ):
            completion = harness_intent_completion.complete_implicit_intent("一个月的")
        assert completion.completed
        assert completion.tool_id == "timescar.dm.query"
        assert completion.canonical_text == "查询 TimesCar 预约 一个月的"
        assert completion.parameter_overrides["requested_hours"] == 24 * 30
        assert completion.inherited_from["trace_id"] == "trace_old"
        saved = json.loads(completion_log.read_text(encoding="utf-8").splitlines()[0])
        assert saved["completed"] is True


def test_implicit_completion_handle_routes_without_business_words() -> None:
    registry = load_registry()
    with tempfile.TemporaryDirectory() as tmp:
        invocation_log = Path(tmp) / "invocations.jsonl"
        completion_log = Path(tmp) / "completions.jsonl"
        invocation_log.write_text(json.dumps({"tool_id": "timescar.dm.query", "trace_id": "trace_old"}, ensure_ascii=False) + "\n", encoding="utf-8")
        with patch.dict(
            router.os.environ,
            {
                "OPENCLAW_HARNESS_TOOL_INVOCATION_LOG": str(invocation_log),
                "OPENCLAW_HARNESS_INTENT_COMPLETION_LOG": str(completion_log),
                "OPENCLAW_HARNESS_INTENT_AUDIT_LOG": str(Path(tmp) / "audit.jsonl"),
                "OPENCLAW_HARNESS_EVALUATION_LOG": str(Path(tmp) / "eval.jsonl"),
            },
        ), patch.object(
            harness_dispatcher,
            "infer_intent_frame",
            return_value=intent_frame(canonical_text="查询 TimesCar 预约 一个月的"),
        ), patch.object(
            router,
            "run_tool",
            return_value=(
                0,
                "TimesCar 预约查询结果\n范围：2026-05-05T00:00+09:00 至 2026-06-04T00:00+09:00（JST）\n状态：未来范围内没有即将开始的预约",
            ),
        ) as run_tool:
            result = router.handle(
                "一个月的",
                "discord_dm",
                "999",
                "2026-05-05T00:00:00+09:00",
                registry_override=registry,
                kernel_root=Path(tmp) / "kernel",
            )
    assert result.status == "ok"
    assert result.classification.tool_id == "timescar.dm.query"
    assert result.args["_intent_completion"]["completed"] is True
    assert result.args["text"] == "查询 TimesCar 预约 一个月的"
    assert run_tool.call_args.args[1]["text"] == "查询 TimesCar 预约 一个月的"


def test_timescar_query_week_evaluator_rejects_24h_result() -> None:
    registry = load_registry()
    tool = next(item for item in registry["tools"] if item["tool_id"] == "timescar.dm.query")
    contract = {"tool_id": "timescar.dm.query", "type": "timescar_query_range", "requested_hours": 24 * 7}
    output = "TimesCar 预约查询结果\n范围：2026-05-05T19:24+09:00 至 2026-05-06T19:24+09:00（JST）\n状态：找到 1 单"
    evaluation = router.evaluate_result(tool, output, contract)
    assert not evaluation.passed
    assert evaluation.gap_type == "registered_tool_parameter_gap"
    assert "168h" in evaluation.reason


def test_executor_capability_gap_is_not_reported_success() -> None:
    registry = load_registry()
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        router.os.environ,
        {
            "OPENCLAW_HARNESS_INTENT_AUDIT_LOG": str(Path(tmp) / "audit.jsonl"),
            "OPENCLAW_HARNESS_EVALUATION_LOG": str(Path(tmp) / "eval.jsonl"),
        },
    ), patch.object(
        harness_dispatcher,
        "infer_intent_frame",
        return_value=intent_frame(canonical_text="查询 TimesCar 预约 未来一周", parameters={"duration_hours": 168, "offset_hours": 0}),
    ), patch.object(
        router,
        "run_tool",
        return_value=(0, "capability_gap: missing verified executor"),
    ):
        result = router.handle(
            "查一下未来一周的订车记录",
            "discord_dm",
            "999",
            "2026-05-04T00:00:00+09:00",
            registry_override=registry,
            kernel_root=Path(tmp) / "kernel",
        )
    assert result.status == "unsupported"
    assert result.route_kind == "registered_tool_capability_gap"
    assert "执行器能力缺口" in result.reply


def test_timescar_book_window_classifies_to_write_tool() -> None:
    result = router.classify("请再预订一单明天早9点到21点的车辆，车型和我惯用的一致。", "discord_dm", "999", load_registry())
    assert result.intent_id == "timescar.reservation_book_window"
    assert result.tool_id == "timescar.dm.book_window"
    assert result.tool and result.tool["write_operation"] is True


def test_timescar_book_available_car_followup_classifies_to_write_tool() -> None:
    result = router.classify("那就把车换成可以预订的车", "discord_dm", "999", load_registry())
    assert result.intent_id == "timescar.reservation_book_window"
    assert result.tool_id == "timescar.dm.book_window"


def test_timescar_adjust_classifies_to_write_tool() -> None:
    result = router.classify(
        "请把明天开始的订车取消明天的时间，让开始时间从后天早上9点开始，结束时间不变。",
        "discord_dm",
        "999",
        load_registry(),
    )
    assert result.intent_id == "timescar.reservation_adjust_start"
    assert result.tool and result.tool["write_operation"] is True


def test_timescar_relative_adjust_followup_classifies_to_write_tool() -> None:
    result = router.classify(
        "把这单的开始时间往后推24小时，结束时间不变。",
        "discord_dm",
        "999",
        load_registry(),
    )
    assert result.intent_id == "timescar.reservation_adjust_start"
    assert result.tool_id == "timescar.dm.adjust_start"
    assert result.tool and result.tool["write_operation"] is True


def test_timescar_tomorrow_relative_adjust_classifies_to_write_tool() -> None:
    result = router.classify(
        "请把明天开始的 TimesCar 订车预约的开始时间往后延 24 小时，结束时间保持不变。",
        "discord_dm",
        "999",
        load_registry(),
    )
    assert result.intent_id == "timescar.reservation_adjust_start"
    assert result.tool_id == "timescar.dm.adjust_start"
    assert result.tool and result.tool["write_operation"] is True


def test_timescar_shift_window_classifies_to_write_tool() -> None:
    result = router.classify(
        "请把马上开始的那单预订帮我往后整体延15分钟。",
        "discord_dm",
        "999",
        load_registry(),
    )
    assert result.intent_id == "timescar.reservation_shift_window"
    assert result.tool_id == "timescar.dm.shift_window"
    assert result.tool and result.tool["write_operation"] is True


def test_model_intent_frame_binds_relative_timescar_adjust_followup() -> None:
    registry = load_registry()
    frame = harness_dispatcher.infer_intent_frame(
        "把这单的开始时间往后推24小时，结束时间不变。",
        context="",
        registry=registry,
        model_caller=lambda _messages: json.dumps(
            {
                "conversation_mode": "task",
                "domain": "timescar",
                "action": "adjust",
                "canonical_text": "将这单 TimesCar 预约开始时间后移 24 小时，结束时间保持不变。",
                "context_refs": [{"type": "recent_timescar_reservation", "selector": "next_reservation_within_48h"}],
                "parameters": {"relative_start_shift_hours": 24, "preserve_return_time": True},
                "safety": "write",
                "result_contract": {"type": "timescar_adjust_start", "preserve_return_time": True},
                "tool_candidates": [{"tool_id": "timescar.dm.adjust_start", "confidence": 0.98, "reason": "semantic contract"}],
                "confidence": 0.98,
                "reason": "semantic TimesCar start adjustment",
            },
            ensure_ascii=False,
        ),
    )
    assert frame.domain == "timescar"
    assert frame.action == "adjust"
    assert frame.safety == "write"
    assert frame.tool_candidates[0]["tool_id"] == "timescar.dm.adjust_start"


def test_model_intent_frame_binds_tomorrow_relative_adjust_followup() -> None:
    registry = load_registry()
    frame = harness_dispatcher.infer_intent_frame(
        "请把明天开始的 TimesCar 订车预约的开始时间往后延 24 小时，结束时间保持不变。",
        context="",
        registry=registry,
        model_caller=lambda _messages: json.dumps(
            {
                "conversation_mode": "task",
                "domain": "timescar",
                "action": "adjust",
                "canonical_text": "将明天开始的 TimesCar 预约开始时间后移 24 小时，结束时间保持不变。",
                "context_refs": [{"type": "recent_timescar_reservation", "selector": "tomorrow_reservation"}],
                "parameters": {"relative_start_shift_hours": 24, "preserve_return_time": True},
                "safety": "write",
                "result_contract": {"type": "timescar_adjust_start", "preserve_return_time": True},
                "tool_candidates": [{"tool_id": "timescar.dm.adjust_start", "confidence": 0.98, "reason": "semantic contract"}],
                "confidence": 0.98,
                "reason": "semantic TimesCar start adjustment",
            },
            ensure_ascii=False,
        ),
    )
    assert frame.domain == "timescar"
    assert frame.action == "adjust"
    assert frame.safety == "write"
    assert frame.tool_candidates[0]["tool_id"] == "timescar.dm.adjust_start"


def test_model_intent_frame_binds_timescar_shift_window_followup() -> None:
    registry = load_registry()
    frame = harness_dispatcher.infer_intent_frame(
        "请把马上开始的那单预订帮我往后整体延15分钟。",
        context="",
        registry=registry,
        model_caller=lambda _messages: json.dumps(
            {
                "conversation_mode": "task",
                "domain": "timescar",
                "action": "adjust",
                "canonical_text": "将马上开始的 TimesCar 预约整体后移 15 分钟，开始和结束一起平移。",
                "context_refs": [{"type": "recent_timescar_reservation", "selector": "next_reservation_within_48h"}],
                "parameters": {"relative_window_shift": True, "preserve_duration": True},
                "safety": "write",
                "result_contract": {"type": "timescar_shift_window", "preserve_duration": True},
                "tool_candidates": [{"tool_id": "timescar.dm.shift_window", "confidence": 0.98, "reason": "semantic contract"}],
                "confidence": 0.98,
                "reason": "semantic TimesCar whole-window shift",
            },
            ensure_ascii=False,
        ),
    )
    assert frame.domain == "timescar"
    assert frame.action == "adjust"
    assert frame.safety == "write"
    assert frame.tool_candidates[0]["tool_id"] == "timescar.dm.shift_window"


def test_timescar_keep_classifies_before_adjust_tool() -> None:
    result = router.classify("请保留明天的订车", "discord_dm", "999", load_registry())
    assert result.intent_id == "timescar.reservation_keep"
    assert result.tool_id == "timescar.dm.keep_next"


def test_timescar_cancel_classifies_before_adjust_tool() -> None:
    result = router.classify("请取消这单订车", "discord_dm", "999", load_registry())
    assert result.intent_id == "timescar.reservation_cancel"
    assert result.tool_id == "timescar.dm.cancel_next"


def test_timescar_cancel_recent_order_classifies_to_cancel_tool() -> None:
    result = router.classify("好的，把刚刚这单取消掉吧", "discord_dm", "999", load_registry())
    assert result.intent_id == "timescar.reservation_cancel"
    assert result.tool_id == "timescar.dm.cancel_next"


def test_timescar_cancel_this_order_classifies_to_cancel_tool() -> None:
    result = router.classify("把这单取消掉", "discord_dm", "999", load_registry())
    assert result.intent_id == "timescar.reservation_cancel"
    assert result.tool_id == "timescar.dm.cancel_next"


def test_timescar_cancel_status_is_readonly_registered_tool() -> None:
    result = router.classify("这单取消了吗？", "discord_dm", "999", load_registry())
    assert result.intent_id == "timescar.reservation_cancel_status"
    assert result.tool_id == "timescar.dm.cancel_status"
    assert result.tool and result.tool["write_operation"] is False


def test_news_1700_maps_to_formal_cron_job() -> None:
    result = router.classify("触发一轮17点的新闻任务", "discord_dm", "999", load_registry())
    assert result.intent_id == "news.cron_run"
    args = router.extract_args(result.tool or {}, "触发一轮17点的新闻任务", "2026-05-04T00:00:00+09:00")
    assert args["job_name"] == "news-digest-jst-1700"


def test_news_makeup_without_slot_maps_to_composite_formal_job() -> None:
    registry = load_registry()
    tool = next(item for item in registry["tools"] if item["tool_id"] == "openclaw.cron.run.news")

    args = router.extract_args(tool, "补发今天没发的新闻", "2026-05-20T22:00:00+09:00")

    assert args["job_name"] == "news-digest-jst-today"


def test_xhs_cron_status_binds_to_readonly_status_tool() -> None:
    registry = load_registry()
    frame = harness_dispatcher.infer_intent_frame(
        "检查每3天一次的小红书文章撰写任务状态。",
        context="",
        registry=registry,
        model_caller=lambda _messages: json.dumps(
            {
                "conversation_mode": "task",
                "domain": "cron",
                "action": "status",
                "canonical_text": "检查每3天一次的小红书文章撰写任务状态。",
                "context_refs": [],
                "parameters": {"topic": "xhs"},
                "safety": "readonly",
                "result_contract": {"type": "cron_status", "topic": "xhs"},
                "tool_candidates": [{"tool_id": "openclaw.cron.status", "confidence": 0.98, "reason": "semantic contract"}],
                "confidence": 0.98,
                "reason": "recurring task status",
            },
            ensure_ascii=False,
        ),
    )
    assert frame.source == "model"
    assert frame.domain == "cron"
    assert frame.action == "status"
    result = router.classify("检查每3天一次的小红书文章撰写任务状态。", "discord_dm", "999", registry)
    assert result.tool_id == "openclaw.cron.status"
    args = router.extract_args(result.tool or {}, frame.canonical_text, "2026-05-04T00:00:00+09:00")
    result.intent_frame = frame.__dict__
    args = router.apply_model_intent_frame(args, result)
    assert args["topic"] == "xhs"


def test_cron_status_model_topic_overrides_registry_default() -> None:
    registry = load_registry()
    tool = next(item for item in registry["tools"] if item["tool_id"] == "openclaw.cron.status")
    classification = router.classification_for_tool_id(
        registry,
        "openclaw.cron.status",
        "semantic cron status",
        intent_frame={
            "conversation_mode": "task",
            "domain": "cron",
            "action": "status",
            "canonical_text": "为什么公共频道的新闻停了？",
            "parameters": {"topic": "news"},
        },
    )
    assert classification is not None
    args = router.extract_args(tool, "为什么公共频道的新闻停了？", "2026-05-20T00:00:00+09:00")
    args = router.apply_model_intent_frame(args, classification)
    assert args["topic"] == "news"


def test_configured_recurring_job_run_binds_to_generic_cron_tool() -> None:
    registry = router.load_registry()
    frame = infer_intent_frame(
        "接下来，请你开始执行每3天一次的小红书撰稿计划。",
        context="",
        registry=registry,
        model_caller=lambda _messages: json.dumps(
            {
                "conversation_mode": "task",
                "domain": "cron",
                "action": "run",
                "canonical_text": "接下来，请你开始执行每3天一次的小红书撰稿计划。",
                "context_refs": [],
                "parameters": {"capability_id": "recurring.content_writing.every_3_days"},
                "safety": "write",
                "result_contract": {"type": "recurring_cron_run", "capability_id": "recurring.content_writing.every_3_days"},
                "tool_candidates": [{"tool_id": "openclaw.cron.run.recurring_job", "confidence": 0.98, "reason": "semantic contract"}],
                "confidence": 0.98,
                "reason": "manual run for configured recurring job",
            },
            ensure_ascii=False,
        ),
    )
    assert frame.domain == "cron"
    assert frame.action == "run"
    assert frame.safety == "write"
    result = router.classification_for_tool_id(registry, frame.tool_candidates[0]["tool_id"], frame.reason, intent_frame=frame.__dict__)
    assert result is not None
    assert result.tool_id == "openclaw.cron.run.recurring_job"
    args = router.extract_args(result.tool or {}, frame.canonical_text, "2026-05-09T00:00:00+09:00")
    assert args["text"] == "接下来，请你开始执行每3天一次的小红书撰稿计划。"


def test_recurring_cron_args_include_reply_channel_id(monkeypatch) -> None:
    tool = {"args_schema": {"mode": "recurring_cron_job_from_text"}}
    monkeypatch.setenv("OPENCLAW_REPLY_CHANNEL_ID", "dm_channel_1")

    args = router.extract_args(tool, "执行任务", "2026-05-09T00:00:00+09:00")

    assert args["reply_channel_id"] == "dm_channel_1"


def test_cron_ack_renders_direct_script_final_report() -> None:
    output = json.dumps(
        {
            "status": "success",
            "job_name": "weather-report-jst-0700",
            "delivery": "manual_owner_reply",
            "final_report": "天气预报\n- 原人自宅：晴朗",
        },
        ensure_ascii=False,
    )

    reply = router.format_reply(
        {"reply_policy": "cron_ack"},
        {"job_name": "weather-report-jst-0700"},
        0,
        output,
    )

    assert "OpenClaw 正式任务已完成。" in reply
    assert "天气预报" in reply
    assert "No running or recent sessions" not in reply


def test_cron_ack_media_already_sent_returns_short_success() -> None:
    output = json.dumps(
        {
            "status": "success",
            "job_name": "weather-report-jst-0700",
            "delivery": "manual_media_sent",
            "final_report": "",
            "media_delivery": "media:/tmp/weather.png",
        },
        ensure_ascii=False,
    )

    reply = router.format_reply({"reply_policy": "cron_ack"}, {"job_name": "weather-report-jst-0700"}, 0, output)

    assert reply == "任务已经触发完成；没有检测到需要展示的最终内容。"


def test_weather_query_maps_to_registered_tool() -> None:
    result = router.classify("请查询明天东京和长野天气、风况和能见度", "discord_dm", "999", load_registry())
    assert result.intent_id == "weather.dm.query"
    assert result.tool_id == "weather.dm.query"
    assert result.tool and result.tool["write_operation"] is False


def test_model_first_selects_registered_tool_before_local_fallback() -> None:
    registry = load_registry()
    with patch.object(
        router,
        "model_classify_intent",
        return_value=(
            router.Classification(
                "timescar.reservation_keep",
                "timescar.dm.keep_next",
                0.93,
                "semantic keep decision",
                next(tool for tool in registry["tools"] if tool["tool_id"] == "timescar.dm.keep_next"),
                {"canonical_text": "请保留明天的订车", "parameters": {}},
            ),
            "registered_task",
        ),
    ) as model_route:
        classification, route_kind = router.classify_intent_model_first(
            "请保留明天的订车",
            "discord_dm",
            "999",
            registry,
            context="previous bot asked whether to cancel the next TimesCar booking",
        )
    model_route.assert_called_once()
    assert route_kind == "registered_task"
    assert classification.tool_id == "timescar.dm.keep_next"


def test_model_first_does_not_fallback_to_local_registered_tool_when_unavailable() -> None:
    registry = load_registry()
    with patch.object(router, "model_classify_intent", side_effect=RuntimeError("offline")):
        classification, route_kind = router.classify_intent_model_first(
            "请保留明天的订车",
            "discord_dm",
            "999",
            registry,
        )
    assert route_kind is None
    assert classification.tool_id is None
    assert "model_first_unavailable=RuntimeError" in classification.reason


def test_model_first_timeout_does_not_fallback_to_timescar_book_window() -> None:
    registry = load_registry()
    with patch.object(router, "model_classify_intent", side_effect=TimeoutError("timed out")):
        classification, route_kind = router.classify_intent_model_first(
            "请再预订一单明天早9点到21点的车辆，车型和我惯用的一致。",
            "discord_dm",
            "999",
            registry,
        )
    assert route_kind is None
    assert classification.tool_id is None
    assert "model_first_unavailable=TimeoutError" in classification.reason


def test_correction_message_binds_to_recent_timescar_query() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "invocations.jsonl"
        log.write_text(
            json.dumps({"tool_id": "timescar.dm.query", "trace_id": "trace_old"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        with patch.dict(harness_intent_audit.os.environ, {"OPENCLAW_HARNESS_TOOL_INVOCATION_LOG": str(log)}):
            assert harness_intent_audit.resolve_correction_tool_id("我说的是未来一周，你查的时间段不对吧？") == "timescar.dm.query"


def test_registered_readonly_parameter_gap_records_plan_without_success_reply() -> None:
    registry = load_registry()
    with tempfile.TemporaryDirectory() as tmp:
        kernel_root = Path(tmp) / "kernel"
        eval_log = Path(tmp) / "eval.jsonl"
        audit_log = Path(tmp) / "audit.jsonl"
        with patch.dict(
            router.os.environ,
            {
                "OPENCLAW_HARNESS_EVALUATION_LOG": str(eval_log),
                "OPENCLAW_HARNESS_INTENT_AUDIT_LOG": str(audit_log),
            },
        ), patch.object(
            harness_dispatcher,
            "infer_intent_frame",
            return_value=intent_frame(canonical_text="查一下未来一周的订车记录", parameters={"duration_hours": 168, "offset_hours": 0, "relation": "within"}),
        ), patch.object(
            router,
            "run_tool",
            return_value=(
                0,
                "TimesCar 预约查询结果\n范围：2026-05-05T19:24+09:00 至 2026-05-06T19:24+09:00（JST）\n状态：找到 1 单",
            ),
        ):
            result = router.handle(
                "查一下未来一周的订车记录",
                "discord_dm",
                "999",
                "2026-05-05T19:24:00+09:00",
                registry_override=registry,
                kernel_root=kernel_root,
                replay_depth=1,
        )
        assert result.status == "unsupported"
        assert result.route_kind == "registered_tool_parameter_gap"
        assert "已拦截" in result.reply
        assert "执行成功" not in result.reply
        assert (kernel_root / "dm_capability_plans.jsonl").exists()
        record = json.loads(eval_log.read_text(encoding="utf-8").splitlines()[0])
        assert record["gap_type"] == "registered_tool_parameter_gap"


def test_model_first_timeout_does_not_fallback_to_available_car_followup() -> None:
    registry = load_registry()
    with patch.object(router, "model_classify_intent", side_effect=TimeoutError("timed out")):
        classification, route_kind = router.classify_intent_model_first(
            "那就把车换成可以预订的车",
            "discord_dm",
            "999",
            registry,
        )
    assert route_kind is None
    assert classification.tool_id is None


def test_model_first_can_select_timescar_cancel_status() -> None:
    registry = load_registry()
    tool = next(item for item in registry["tools"] if item["tool_id"] == "timescar.dm.cancel_status")
    with patch.object(
        router,
        "model_classify_intent",
        return_value=(
            router.Classification(
                "timescar.reservation_cancel_status",
                "timescar.dm.cancel_status",
                0.95,
                "asks whether the previous cancellation succeeded",
                tool,
                {"canonical_text": "这单取消了吗？", "parameters": {}},
            ),
            "registered_task",
        ),
    ):
        classification, route_kind = router.classify_intent_model_first("这单取消了吗？", "discord_dm", "999", registry)
    assert route_kind == "registered_task"
    assert classification.tool_id == "timescar.dm.cancel_status"


def test_model_first_no_longer_overrides_model_with_timescar_guard() -> None:
    registry = load_registry()
    adjust_tool = next(item for item in registry["tools"] if item["tool_id"] == "timescar.dm.adjust_start")
    with patch.object(
        router,
        "model_classify_intent",
        return_value=(
            router.Classification(
                "timescar.reservation_adjust_start",
                "timescar.dm.adjust_start",
                0.91,
                "model confused cancellation wording with adjust",
                adjust_tool,
                {"canonical_text": "好的，把刚刚这单取消掉吧", "parameters": {}},
            ),
            "registered_task",
        ),
    ):
        classification, route_kind = router.classify_intent_model_first("好的，把刚刚这单取消掉吧", "discord_dm", "999", registry)
    assert route_kind == "registered_task"
    assert classification.tool_id == "timescar.dm.adjust_start"
    assert "guarded" not in classification.reason


def test_timescar_adjust_with_cancel_time_phrase_stays_adjust() -> None:
    registry = load_registry()
    with patch.object(router, "model_classify_intent", side_effect=RuntimeError("offline")):
        classification, route_kind = router.classify_intent_model_first(
            "请把明天开始的订车取消明天的时间，让开始时间从后天早上9点开始，结束时间不变。",
            "discord_dm",
            "999",
            registry,
        )
    assert route_kind is None
    assert classification.tool_id is None


def test_unknown_records_gap_and_returns_ack() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        kernel_root = Path(tmp) / "kernel"
        with patch.object(router, "run_tool") as run_tool, patch.object(
            router, "model_classify_unregistered_intent", return_value=("ambiguous_gap", "asks to create capability")
        ):
            result = router.handle(
                "汤猴，给我发明一个现在不存在的控制台能力。",
                "discord_dm",
                "999",
                "2026-05-04T00:00:00+09:00",
                kernel_root=kernel_root,
            )
            run_tool.assert_not_called()
        assert result.status == "unsupported"
        assert "未执行" in result.reply
        assert (kernel_root / "dm_capability_plans.jsonl").is_file()


def test_chat_only_passes_through_without_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        kernel_root = Path(tmp) / "kernel"
        with patch.object(router, "run_tool") as run_tool, patch.object(
            harness_dispatcher,
            "infer_intent_frame",
            return_value=intent_frame(mode="chat", domain="general", action="chat", canonical_text="我在。", tool_id=None),
        ):
            result = router.handle(
                "还活着吗",
                "discord_dm",
                "999",
                "2026-05-04T00:00:00+09:00",
                kernel_root=kernel_root,
            )
            run_tool.assert_not_called()
        assert result.status == "chat"
        assert result.route_kind == "chat"
        assert result.reply == "我在。"
        assert not (kernel_root / "intent_tool_router_gaps.jsonl").exists()


def test_chat_reply_reports_model_failure_without_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        kernel_root = Path(tmp) / "kernel"
        with patch.object(harness_dispatcher, "infer_intent_frame", side_effect=RuntimeError("offline")):
            result = router.handle(
                "还活着吗",
                "discord_dm",
                "999",
                "2026-05-04T00:00:00+09:00",
                kernel_root=kernel_root,
            )
        assert result.status == "unsupported"
        assert result.route_kind == "intent_model_unavailable"
        assert "意图模型不可用" in result.reply
        assert (kernel_root / "dm_capability_plans.jsonl").exists()


def test_unregistered_task_records_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        kernel_root = Path(tmp) / "kernel"
        with patch.object(router, "run_tool") as run_tool, patch.object(
            harness_dispatcher,
            "infer_intent_frame",
            return_value=intent_frame(mode="gap", domain="unknown", action="gap", canonical_text="请帮我接入一个新的控制台能力。", tool_id=None),
        ):
            result = router.handle(
                "请帮我接入一个新的控制台能力。",
                "discord_dm",
                "999",
                "2026-05-04T00:00:00+09:00",
                kernel_root=kernel_root,
            )
            run_tool.assert_not_called()
        assert result.status == "unsupported"
        assert result.route_kind == "gap"
        assert (kernel_root / "dm_capability_plans.jsonl").exists()


def test_unregistered_safe_readonly_gap_promotes_and_replays() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        registry = load_registry()
        registry["tools"] = [tool for tool in registry["tools"] if tool["tool_id"] != "weather.dm.query"]
        registry_path = Path(tmp) / "intent_tools.json"
        registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
        kernel_root = Path(tmp) / "kernel"
        repair_result = SimpleNamespace(
            status="promoted",
            gap_ref="kernel_session=session_test gap_id=gap_test",
            replay_allowed=True,
            registry_tool=registry_tool("weather.dm.query"),
        )
        with patch.object(
            harness_dispatcher,
            "infer_intent_frame",
            return_value=intent_frame(domain="weather", action="query", canonical_text="请查询明天东京和长野天气、风况和能见度", tool_id="weather.dm.query"),
        ), patch.object(harness_dispatcher, "run_repair", return_value=repair_result) as run_repair, patch.object(
            router, "run_tool", return_value=(0, "天气查询结果")
        ) as run_tool:
            result = router.handle(
                "请查询明天东京和长野天气、风况和能见度",
                "discord_dm",
                "999",
                "2026-05-04T00:00:00+09:00",
                registry_path=registry_path,
                kernel_root=kernel_root,
            )
        run_repair.assert_called_once()
        run_tool.assert_called_once()
        assert result.status == "ok"
        assert result.route_kind in {"registered_task", "registered_task_replayed"}
        assert "自演进：已修复并重试。" in result.reply


def test_unregistered_write_gap_does_not_execute() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        kernel_root = Path(tmp) / "kernel"
        with patch.object(harness_dispatcher, "infer_intent_frame", side_effect=RuntimeError("offline")), patch.object(
            router, "run_tool"
        ) as run_tool:
            result = router.handle(
                "请帮我修改配置并重启服务",
                "discord_dm",
                "999",
                "2026-05-04T00:00:00+09:00",
                kernel_root=kernel_root,
            )
        run_tool.assert_not_called()
        assert result.status == "unsupported"
        assert result.route_kind == "intent_model_unavailable"
        assert "意图模型不可用" in result.reply


def test_unregistered_intent_falls_back_when_model_unavailable() -> None:
    with patch.object(router, "model_classify_unregistered_intent", side_effect=RuntimeError("offline")):
        route_kind, reason = router.classify_unregistered_intent("请帮我接入一个新的控制台能力。")
    assert route_kind == "ambiguous_gap"
    assert "model_unavailable_conservative=RuntimeError" in reason


def test_run_tool_keeps_stderr_out_of_user_output() -> None:
    tool = {
        "intent_id": "test.intent",
        "tool_id": "test.tool",
        "entrypoint": "scripts/openclaw/intent_tool_router.py",
        "args_schema": {"mode": "dm_text_timestamp"},
    }
    args = {"text": "hello", "message_timestamp": "2026-05-04T00:00:00+09:00", "force": False}
    completed = SimpleNamespace(
        returncode=0,
        stdout="业务结果\n",
        stderr="(node:1) [DEP0169] warning\n",
    )
    with tempfile.TemporaryDirectory() as tmp:
        diag = Path(tmp) / "diag.jsonl"
        with patch.dict(router.os.environ, {"OPENCLAW_INTENT_TOOL_DIAG_LOG": str(diag)}), patch.object(
            router.subprocess, "run", return_value=completed
        ):
            code, output = router.run_tool(tool, args, 10)
        assert code == 0
        assert output == "业务结果"
        assert "DEP0169" not in output
        record = json.loads(diag.read_text(encoding="utf-8").splitlines()[0])
        assert record["tool_id"] == "test.tool"
        assert "DEP0169" in record["stderr"]


def test_cron_ack_prefers_final_report_over_raw_json() -> None:
    tool = {"reply_policy": "cron_ack"}
    output = json.dumps(
        {
            "status": "success",
            "job_name": "content-job",
            "final_report": "已完成。\nhttps://docs.example/doc",
            "diagnostics": {"stderr_hidden": True},
        },
        ensure_ascii=False,
    )

    reply = router.format_reply(tool, {}, 0, output)

    assert "OpenClaw 正式任务已完成。" in reply
    assert "任务：content-job" in reply
    assert "https://docs.example/doc" in reply
    assert "stderr_hidden" not in reply


def test_cron_ack_running_reports_tracking_not_completion() -> None:
    tool = {"reply_policy": "cron_ack"}
    output = json.dumps(
        {
            "status": "running",
            "job_name": "content-job",
            "long_task_id": "long_abc",
            "stdout": "{\"ok\":true,\"enqueued\":true}",
        },
        ensure_ascii=False,
    )

    reply = router.format_reply(tool, {}, 0, output)

    assert "长任务已启动并进入跟踪" in reply
    assert "长任务状态：正在进行" in reply
    assert "不代表任务已完成" in reply
    assert "正式任务已完成" not in reply
    assert "enqueued" not in reply


def test_discord_patch_uses_stdout_only_for_user_reply() -> None:
    source = (router.REPO / "scripts" / "openclaw" / "patch_discord_timescar_dm_preroute.py").read_text(encoding="utf-8")
    assert "[stdout, stderr].filter" not in source
    assert "const output = String(stdout || \"\").trim();" in source
    assert "console.warn(\"[springmonkey-intent-tool-router][stderr]\"" in source
    assert '"--context"' in source


def test_create_capability_falls_back_to_unsupported_task() -> None:
    with patch.object(router, "model_classify_unregistered_intent", side_effect=RuntimeError("offline")):
        route_kind, reason = router.classify_unregistered_intent("汤猴，给我发明一个现在不存在的控制台能力。")
    assert route_kind == "ambiguous_gap"
    assert "model_unavailable_conservative=RuntimeError" in reason


def test_classify_only_does_not_execute_tool() -> None:
    registry = load_registry()
    with patch.object(router, "model_classify_intent", side_effect=RuntimeError("offline")):
        result, route_kind = router.classify_intent_model_first("触发一轮17点的新闻任务", "discord_dm", "999", registry)
    assert route_kind is None
    assert result.tool_id is None
