from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import intent_tool_router as router


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
            router, "model_classify_unregistered_intent", return_value=("unsupported_task", "asks to create capability")
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
        assert "未执行，已记录能力缺口" in result.reply
        gap_log = kernel_root / "intent_tool_router_gaps.jsonl"
        assert gap_log.is_file()
        first = json.loads(gap_log.read_text(encoding="utf-8").splitlines()[0])
        assert first["status"] == "open"


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
            router, "model_classify_unregistered_intent", return_value=("unsupported_task", "asks to add capability")
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
        assert result.route_kind == "unsupported_task"
        assert "asks to add capability" in result.reply
        assert (kernel_root / "intent_tool_router_gaps.jsonl").exists()


def test_unregistered_intent_falls_back_when_model_unavailable() -> None:
    with patch.object(router, "model_classify_unregistered_intent", side_effect=RuntimeError("offline")):
        route_kind, reason = router.classify_unregistered_intent("请帮我接入一个新的控制台能力。")
    assert route_kind == "unsupported_task"
    assert "model_unavailable_fallback=RuntimeError" in reason


def test_create_capability_falls_back_to_unsupported_task() -> None:
    with patch.object(router, "model_classify_unregistered_intent", side_effect=RuntimeError("offline")):
        route_kind, reason = router.classify_unregistered_intent("汤猴，给我发明一个现在不存在的控制台能力。")
    assert route_kind == "unsupported_task"
    assert "model_unavailable_fallback=RuntimeError" in reason


def test_classify_only_does_not_execute_tool() -> None:
    result = router.classify("触发一轮17点的新闻任务", "discord_dm", "999", load_registry())
    args = router.extract_args(result.tool or {}, "触发一轮17点的新闻任务", "2026-05-04T00:00:00+09:00")
    assert result.tool_id == "openclaw.cron.run.news"
    assert args == {"job_name": "news-digest-jst-1700"}
