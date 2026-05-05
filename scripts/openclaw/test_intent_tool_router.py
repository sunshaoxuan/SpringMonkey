from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import intent_tool_router as router
import harness_intent_audit
import harness_intent_completion
import nl_time_range
from dm_capability_gap_runner import CapabilityPlan, GapRunnerResult, WEATHER_DM_QUERY_TOOL


def load_registry() -> dict:
    return router.load_registry()


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
        ), patch.object(router, "model_classify_intent", side_effect=RuntimeError("offline")), patch.object(
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


def test_model_first_falls_back_to_local_registered_tool_when_unavailable() -> None:
    registry = load_registry()
    with patch.object(router, "model_classify_intent", side_effect=RuntimeError("offline")):
        classification, route_kind = router.classify_intent_model_first(
            "请保留明天的订车",
            "discord_dm",
            "999",
            registry,
        )
    assert route_kind == "registered_task"
    assert classification.tool_id == "timescar.dm.keep_next"
    assert "model_first_unavailable=RuntimeError" in classification.reason


def test_model_first_timeout_falls_back_to_timescar_book_window() -> None:
    registry = load_registry()
    with patch.object(router, "model_classify_intent", side_effect=TimeoutError("timed out")):
        classification, route_kind = router.classify_intent_model_first(
            "请再预订一单明天早9点到21点的车辆，车型和我惯用的一致。",
            "discord_dm",
            "999",
            registry,
        )
    assert route_kind == "registered_task"
    assert classification.tool_id == "timescar.dm.book_window"
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
        ), patch.object(router, "model_classify_intent", side_effect=RuntimeError("offline")), patch.object(
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


def test_model_first_timeout_falls_back_to_available_car_followup() -> None:
    registry = load_registry()
    with patch.object(router, "model_classify_intent", side_effect=TimeoutError("timed out")):
        classification, route_kind = router.classify_intent_model_first(
            "那就把车换成可以预订的车",
            "discord_dm",
            "999",
            registry,
        )
    assert route_kind == "registered_task"
    assert classification.tool_id == "timescar.dm.book_window"


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


def test_timescar_guard_overrides_model_adjust_for_cancel_followup() -> None:
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
    assert classification.tool_id == "timescar.dm.cancel_next"
    assert "guarded" in classification.reason


def test_timescar_adjust_with_cancel_time_phrase_stays_adjust() -> None:
    registry = load_registry()
    with patch.object(router, "model_classify_intent", side_effect=RuntimeError("offline")):
        classification, route_kind = router.classify_intent_model_first(
            "请把明天开始的订车取消明天的时间，让开始时间从后天早上9点开始，结束时间不变。",
            "discord_dm",
            "999",
            registry,
        )
    assert route_kind == "registered_task"
    assert classification.tool_id == "timescar.dm.adjust_start"


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
            router, "model_classify_unregistered_intent", return_value=("chat", "small talk")
        ) as model_classify, patch.object(router, "model_chat_reply", return_value="我在。") as model_chat:
            result = router.handle(
                "还活着吗",
                "discord_dm",
                "999",
                "2026-05-04T00:00:00+09:00",
                kernel_root=kernel_root,
            )
            run_tool.assert_not_called()
            model_classify.assert_called_once()
            model_chat.assert_called_once()
        assert result.status == "chat"
        assert result.route_kind == "chat"
        assert result.classification.reason == "small talk"
        assert result.reply == "我在。"
        assert not (kernel_root / "intent_tool_router_gaps.jsonl").exists()


def test_chat_reply_reports_model_failure_without_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        kernel_root = Path(tmp) / "kernel"
        with patch.object(router, "model_classify_unregistered_intent", return_value=("chat", "small talk")), patch.object(
            router, "model_chat_reply", side_effect=RuntimeError("offline")
        ):
            result = router.handle(
                "还活着吗",
                "discord_dm",
                "999",
                "2026-05-04T00:00:00+09:00",
                kernel_root=kernel_root,
            )
        assert result.status == "chat"
        assert "聊天模型暂时不可用" in result.reply
        assert not (kernel_root / "intent_tool_router_gaps.jsonl").exists()


def test_unregistered_task_records_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        kernel_root = Path(tmp) / "kernel"
        with patch.object(router, "run_tool") as run_tool, patch.object(
            router, "model_classify_unregistered_intent", return_value=("ambiguous_gap", "asks to add capability")
        ) as model_classify:
            result = router.handle(
                "请帮我接入一个新的控制台能力。",
                "discord_dm",
                "999",
                "2026-05-04T00:00:00+09:00",
                kernel_root=kernel_root,
            )
            run_tool.assert_not_called()
            model_classify.assert_called_once()
        assert result.status == "unsupported"
        assert result.route_kind == "ambiguous_gap"
        assert "asks to add capability" in result.reply
        assert (kernel_root / "dm_capability_plans.jsonl").exists()


def test_unregistered_safe_readonly_gap_promotes_and_replays() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        registry = load_registry()
        registry["tools"] = [tool for tool in registry["tools"] if tool["tool_id"] != "weather.dm.query"]
        registry_path = Path(tmp) / "intent_tools.json"
        registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
        kernel_root = Path(tmp) / "kernel"
        plan = CapabilityPlan(
            capability_id="capability_test",
            source_gap_id="gap_test",
            safety_class="auto_safe_readonly",
            tool_id="weather.dm.query",
            entrypoint="scripts/weather/handle_dm_weather_query.py",
            registry_patch=WEATHER_DM_QUERY_TOOL,
            verify_commands=[],
            replay_text="请查询明天东京和长野天气、风况和能见度",
            status="promoted_replay_ready",
            reason="public read-only query wording",
        )
        gap_result = GapRunnerResult(
            status="promoted",
            safety_class="auto_safe_readonly",
            plan=plan,
            gap_ref="kernel_session=session_test gap_id=gap_test",
            reply="ready",
            registry_tool=WEATHER_DM_QUERY_TOOL,
        )
        with patch.object(
            router, "model_classify_unregistered_intent", return_value=("auto_safe_readonly_gap", "weather lookup")
        ), patch.object(router, "run_gap", return_value=gap_result) as run_gap, patch.object(
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
        run_gap.assert_called_once()
        run_tool.assert_called_once()
        assert result.status == "ok"
        assert result.route_kind == "auto_promoted_replay"
        assert "_capability_gap_plan" in result.args
        assert "天气查询结果" in result.reply


def test_unregistered_write_gap_does_not_execute() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        kernel_root = Path(tmp) / "kernel"
        with patch.object(router, "model_classify_unregistered_intent", return_value=("unsafe_gap", "write operation")), patch.object(
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
        assert result.route_kind == "unsafe_gap"
        assert "不能自动执行" in result.reply


def test_unregistered_intent_falls_back_when_model_unavailable() -> None:
    with patch.object(router, "model_classify_unregistered_intent", side_effect=RuntimeError("offline")):
        route_kind, reason = router.classify_unregistered_intent("请帮我接入一个新的控制台能力。")
    assert route_kind == "ambiguous_gap"
    assert "model_unavailable_fallback=RuntimeError" in reason


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
    assert "model_unavailable_fallback=RuntimeError" in reason


def test_classify_only_does_not_execute_tool() -> None:
    registry = load_registry()
    with patch.object(router, "model_classify_intent", side_effect=RuntimeError("offline")):
        result, route_kind = router.classify_intent_model_first("触发一轮17点的新闻任务", "discord_dm", "999", registry)
    args = router.extract_args(result.tool or {}, "触发一轮17点的新闻任务", "2026-05-04T00:00:00+09:00")
    assert route_kind == "registered_task"
    assert result.tool_id == "openclaw.cron.run.news"
    assert args == {"job_name": "news-digest-jst-1700"}
