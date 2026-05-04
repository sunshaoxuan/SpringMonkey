from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import intent_tool_router as router
from dm_capability_gap_runner import CapabilityPlan, GapRunnerResult, WEATHER_DM_QUERY_TOOL


def load_registry() -> dict:
    return router.load_registry()


def test_timescar_query_classifies_to_registered_tool() -> None:
    result = router.classify("汤猴，检查一下未来48小时的订车记录。", "discord_dm", "999", load_registry())
    assert result.intent_id == "timescar.reservation_query"
    assert result.tool_id == "timescar.dm.query"


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


def test_create_capability_falls_back_to_unsupported_task() -> None:
    with patch.object(router, "model_classify_unregistered_intent", side_effect=RuntimeError("offline")):
        route_kind, reason = router.classify_unregistered_intent("汤猴，给我发明一个现在不存在的控制台能力。")
    assert route_kind == "ambiguous_gap"
    assert "model_unavailable_fallback=RuntimeError" in reason


def test_classify_only_does_not_execute_tool() -> None:
    result = router.classify("触发一轮17点的新闻任务", "discord_dm", "999", load_registry())
    args = router.extract_args(result.tool or {}, "触发一轮17点的新闻任务", "2026-05-04T00:00:00+09:00")
    assert result.tool_id == "openclaw.cron.run.news"
    assert args == {"job_name": "news-digest-jst-1700"}
