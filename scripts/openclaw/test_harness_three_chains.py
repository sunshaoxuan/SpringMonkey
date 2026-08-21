from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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


def test_dispatcher_records_unified_trial_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as tmp, patch.dict(
        os.environ,
        {
            "OPENCLAW_HARNESS_TRIAL_LOG": str(Path(tmp) / "trials.jsonl"),
            "OPENCLAW_HARNESS_REPORT_LOG": str(Path(tmp) / "reports.jsonl"),
            "OPENCLAW_HARNESS_MODEL_CALL_LOG": str(Path(tmp) / "models.jsonl"),
        },
    ):
        result = handle_event(
            text="你好",
            channel="discord_dm",
            user_id="999666719356354610",
            message_timestamp="2026-05-05T00:00:00+09:00",
            registry={"tools": []},
            context="",
            kernel_root=Path(tmp) / "kernel",
            timeout_seconds=10,
            extract_args=lambda _tool, _text, _ts: {},
            run_tool=lambda _tool, _args, _timeout: (0, ""),
            format_reply=lambda _tool, _args, _code, output: output,
            audit_intent=lambda **_kwargs: None,
            evaluate_result=lambda _tool, _output, _contract: None,
            model_caller=lambda _messages: json.dumps(
                {
                    "conversation_mode": "chat",
                    "domain": "general",
                    "action": "chat",
                    "canonical_text": "你好，我在。",
                    "context_refs": [],
                    "parameters": {},
                    "safety": "readonly",
                    "result_contract": {},
                    "tool_candidates": [],
                    "confidence": 0.99,
                    "reason": "greeting",
                },
                ensure_ascii=False,
            ),
        )
        rows = [json.loads(line) for line in (Path(tmp) / "trials.jsonl").read_text(encoding="utf-8").splitlines()]

    assert result.status == "chat"
    assert rows[-1]["trace_id"].startswith("trace_")
    assert rows[-1]["task_id"].startswith("task_")
    assert rows[-1]["status"] == "chat"
    assert rows[-1]["outcome"] == "completed"


def test_dispatcher_does_not_claim_replay_fixed_when_replay_still_fails() -> None:
    frame = {
        "conversation_mode": "gap",
        "domain": "config",
        "action": "update",
        "canonical_text": "升级已有工作流",
        "context_refs": [],
        "parameters": {},
        "safety": "write",
        "result_contract": {},
        "tool_candidates": [],
        "confidence": 0.9,
        "reason": "no tool can update this workflow",
    }

    with tempfile.TemporaryDirectory() as tmp, patch(
        "harness_dispatcher.run_repair",
        return_value=SimpleNamespace(
            replay_allowed=True,
            registry_tool={"tool_id": "fake.generated", "entrypoint": "scripts/fake.py", "write_operation": False},
            gap_ref="gap_ref=test",
            status="promoted",
        ),
    ):
        result = handle_event(
            text="升级已有工作流",
            channel="discord_dm",
            user_id="999666719356354610",
            message_timestamp="2026-05-05T00:00:00+09:00",
            registry={"tools": []},
            context="",
            kernel_root=Path(tmp) / "kernel",
            timeout_seconds=10,
            extract_args=lambda _tool, _text, _ts: {},
            run_tool=lambda _tool, _args, _timeout: (0, ""),
            format_reply=lambda _tool, _args, _code, output: output,
            audit_intent=lambda **_kwargs: None,
            evaluate_result=lambda _tool, _output, _contract: None,
            model_caller=lambda _messages: json.dumps(frame, ensure_ascii=False),
        )

    assert result.status == "unsupported"
    assert "自演进：已尝试重放，但原任务仍未完成。" in result.reply
    assert "自演进：已修复并重试。" not in result.reply


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
    assert "阶段：evaluate" not in reply
    assert "工具：timescar.dm.cancel_next" not in reply
    assert "回查：target_booking_absent_after_success" not in reply
    assert "详细诊断：后台日志保留" in reply


def test_reporter_suppresses_links_by_default() -> None:
    envelope = ReportEnvelope(
        task_id="task_link",
        trace_id="trace_link",
        status="ok",
        visibility="owner_dm",
        summary="结论：已查到。来源：https://example.com/path",
        diagnostics_ref="trace_id=trace_link route=registered_task",
    )
    reply = format_owner_reply(envelope)
    assert "https://example.com" not in reply
    assert "链接已记录后台" in reply
    assert "触发状态：成功" not in reply
    assert "详细诊断：后台日志保留" not in reply
    assert reply.endswith("---")


def test_reporter_can_allow_links_explicitly() -> None:
    envelope = ReportEnvelope(
        task_id="task_link",
        trace_id="trace_link",
        status="ok",
        visibility="owner_dm",
        summary="结论：已查到。来源：https://example.com/path",
        diagnostics_ref="trace_id=trace_link route=registered_task",
        allow_links=True,
    )
    assert "https://example.com/path" in format_owner_reply(envelope)


def test_reporter_extracts_text_from_structured_command_array() -> None:
    envelope = ReportEnvelope(
        task_id="task_command",
        trace_id="trace_command",
        status="ok",
        visibility="owner_dm",
        summary=json.dumps(
            [
                {"type": "text", "text": "2df6aa0"},
                {"content": [{"type": "text", "text": "official_runtime_shadow=ok"}]},
                [],
            ],
            ensure_ascii=False,
            indent=2,
        ),
        diagnostics_ref="trace_id=trace_command route=registered_task",
    )

    reply = format_owner_reply(envelope)

    assert "2df6aa0" in reply
    assert "official_runtime_shadow=ok" in reply
    assert "]," not in reply


def test_reporter_discards_json_punctuation_only_lines() -> None:
    envelope = ReportEnvelope(
        task_id="task_broken_json",
        trace_id="trace_broken_json",
        status="ok",
        visibility="owner_dm",
        summary="[\n],\n]\n",
        diagnostics_ref="trace_id=trace_broken_json route=registered_task",
    )

    reply = format_owner_reply(envelope)

    assert "]," not in reply
    assert "任务已处理" in reply


def test_cron_status_success_preserves_delivery_evidence_lines() -> None:
    output = "\n".join(
        [
            "OpenClaw 定时任务状态",
            "主题：news",
            "任务总数：12",
            "匹配数量：2",
            "结论：匹配任务 2 个；直发 cron 启用 2 个；今天未找到 direct cron 成功投递记录。",
            "",
            "1.",
            "任务：news-digest-jst-0900 | 内部：disabled | 直发：enabled | 直发计划：0 9 * * * | 频道：1483636573235843072",
            "最近执行：成功",
            "开始：2026-05-18T09:00:01",
            "今天是否执行过：否",
            "投递：delivered",
            "",
            "2.",
            "任务：news-digest-jst-1700 | 内部：disabled | 直发：enabled | 直发计划：0 17 * * * | 频道：1483636573235843072",
            "最近执行：成功",
            "开始：2026-05-18T17:00:01",
            "今天是否执行过：否",
            "投递：delivered",
        ]
    )
    envelope = ReportEnvelope(
        task_id="cron_status",
        trace_id="trace_cron",
        status="ok",
        visibility="owner_dm",
        summary=output,
        diagnostics_ref="trace_id=trace_cron route=registered_task",
    )

    reply = format_owner_reply(envelope)

    assert "news-digest-jst-0900" in reply
    assert "news-digest-jst-1700" in reply
    assert "今天是否执行过：否" in reply
    assert "投递：delivered" in reply
    assert "详细诊断：后台日志保留" not in reply


def test_reporter_keeps_failure_and_tracking_as_structured_reports() -> None:
    failed = ReportEnvelope(
        task_id="task_failed",
        trace_id="trace_failed",
        status="failed",
        visibility="owner_dm",
        summary="工具失败。",
        diagnostics_ref="trace_id=trace_failed route=execute",
        failure_type="executor_failed",
    )
    tracking = ReportEnvelope(
        task_id="task_tracking",
        trace_id="trace_tracking",
        status="tracking",
        visibility="owner_dm",
        summary="长任务已启动。",
        diagnostics_ref="trace_id=trace_tracking route=binding",
    )

    assert "触发状态：失败" in format_owner_reply(failed)
    assert "详细诊断：后台日志保留" in format_owner_reply(failed)
    assert "触发状态：已启动" in format_owner_reply(tracking)


def test_reporter_summarizes_web_research_without_sources_or_evidence() -> None:
    envelope = ReportEnvelope(
        task_id="task_web",
        trace_id="trace_web",
        status="ok",
        visibility="owner_dm",
        tool_id="openclaw.web.research",
        summary=(
            "联网检索结果\n"
            "状态：成功\n"
            "- 结论一。\n"
            "- 结论二。\n"
            "来源：\n"
            "1. Example - https://example.com\n"
            "检索证据：search_attempted=true fetch_attempted=true browser_attempted=false sources=1"
        ),
        diagnostics_ref="trace_id=trace_web route=registered_task",
    )
    reply = format_owner_reply(envelope)
    assert "来源：" not in reply
    assert "检索证据" not in reply
    assert "https://example.com" not in reply
    assert "结论一" in reply


def test_reporter_hides_self_repair_diagnostics_from_owner_reply() -> None:
    envelope = ReportEnvelope(
        task_id="task_gap",
        trace_id="trace_gap",
        status="unsupported",
        visibility="owner_dm",
        summary=(
            "未执行：需要补齐内部自演进能力。\n"
            "记录：kernel_session=session_x gap_id=gap_y plan_log=/var/lib/openclaw/kernel/dm.jsonl\n"
            "自演进：promoted\n"
            "重放判定：允许，promoted read-only repair package can be replayed once\n"
            "工具匠：promoted\n"
            "事件日志：/tmp/openclaw/capability_gap_events.jsonl"
        ),
        diagnostics_ref="trace_id=trace_gap route=gap",
        stage="binding",
        failure_type="tool_binding_gap",
    )
    reply = format_owner_reply(envelope)
    assert "未执行：需要补齐内部自演进能力。" in reply
    assert "kernel_session" not in reply
    assert "gap_id" not in reply
    assert "事件日志" not in reply
    assert "详细诊断：后台日志保留" in reply


def test_repair_started_summary_includes_tracking_identifiers() -> None:
    import harness_dispatcher

    class Repair:
        implementation_run = {
            "long_task_id": "long_abc",
            "run_id": "impl_abc",
        }

    summary = harness_dispatcher.capability_gap_user_summary("repair_started", Repair())

    assert "跟踪编号：long_abc" in summary
    assert "实现编号：impl_abc" in summary
    assert "检查长任务状态" in summary
    assert "结果投递" in summary


def test_repair_started_reports_tracking_trigger_status() -> None:
    import harness_dispatcher

    class Repair:
        status = "repair_started"
        gap_ref = "kernel_session=session_x gap_id=gap_y"
        replay_allowed = False
        registry_tool = None
        implementation_run = {
            "long_task_id": "long_abc",
            "run_id": "impl_abc",
        }

    def model_caller(_messages: list[dict[str, str]]) -> str:
        return json.dumps(
            {
                "conversation_mode": "task",
                "domain": "weather",
                "action": "implement",
                "canonical_text": "实现天气任务变更",
                "context_refs": [],
                "parameters": {},
                "safety": "write",
                "result_contract": {},
                "tool_candidates": [],
                "confidence": 0.95,
                "reason": "requires implementation",
            },
            ensure_ascii=False,
        )

    with tempfile.TemporaryDirectory() as tmp, patch.object(harness_dispatcher, "run_repair", return_value=Repair()):
        result = handle_event(
            text="实现天气任务变更",
            channel="discord_dm",
            user_id="999666719356354610",
            message_timestamp="2026-05-19T00:00:00+09:00",
            registry={"tools": []},
            context="",
            kernel_root=Path(tmp) / "kernel",
            timeout_seconds=10,
            extract_args=lambda _tool, _text, _ts: {},
            run_tool=lambda _tool, _args, _timeout: (0, ""),
            format_reply=lambda _tool, _args, _code, output: output,
            audit_intent=lambda **_kwargs: None,
            evaluate_result=lambda _tool, _output, _contract: None,
            model_caller=model_caller,
        )

    assert result.status == "tracking"
    assert "触发状态：已启动" in result.reply
    assert "未执行" not in result.reply
    assert "跟踪编号：long_abc" in result.reply


def test_reporter_summarizes_generated_helper_json_reply() -> None:
    envelope = ReportEnvelope(
        task_id="task_self",
        trace_id="trace_self",
        status="ok",
        visibility="owner_dm",
        summary=json.dumps(
            {
                "status": "success",
                "tool_id": "openclaw.generated.registry_missing",
                "result": (
                    "自演进状态\n"
                    "已推广 helper：3\n"
                    "未解决缺口：2\n"
                    "1. stage=binding status=promoted safety=auto_safe_readonly replay=True "
                    "tool=openclaw.generated.registry_missing lifecycle=recorded -> promoted"
                ),
            },
            ensure_ascii=False,
        ),
        diagnostics_ref="trace_id=trace_self route=registered_task",
        stage="report",
        tool_id="openclaw.generated.registry_missing",
    )
    reply = format_owner_reply(envelope)
    assert "自演进处理完成" in reply
    assert "已推广 helper：3" in reply
    assert "下一步：可以直接重试原任务" in reply
    assert "stage=binding" not in reply
    assert "{\"status\"" not in reply


def test_discord_patch_does_not_add_business_router_success_prefix() -> None:
    source = (Path(__file__).resolve().parent / "patch_discord_timescar_dm_preroute.py").read_text(encoding="utf-8")
    assert "汤猴私信任务已由通用事件路由处理。" not in source
    assert "汤猴已收到私信，正在通过事件入口处理" not in source
    assert "汤猴私信任务路由失败" in source


def test_router_json_exposes_report_envelope_and_context_summary() -> None:
    import intent_tool_router as router
    import harness_dispatcher
    from harness_intent_agent import IntentFrame
    from unittest.mock import patch

    registry = router.load_registry()
    frame = IntentFrame(
        conversation_mode="task",
        domain="timescar",
        action="cancel",
        canonical_text="取消 TimesCar 明天预约",
        context_refs=[],
        parameters={},
        safety="write",
        result_contract={},
        tool_candidates=[{"tool_id": "timescar.dm.cancel_next", "confidence": 0.95, "reason": "test"}],
        confidence=0.95,
        reason="test",
    )
    with tempfile.TemporaryDirectory() as tmp, patch.object(harness_dispatcher, "infer_intent_frame", return_value=frame):
        result = router.handle(
            "请取消明天的TimesCar预约",
            "discord_public",
            "999666719356354610",
            "2026-05-05T00:00:00+09:00",
            registry_override=registry,
            kernel_root=Path(tmp) / "kernel",
        )
    assert result.route_kind == "governance_denied"
    assert result.report
    assert result.report["visibility"] == "owner_dm"
    assert result.report["failure_type"] == "governance_denied"
    assert result.context_summary and result.context_summary["trace_id"].startswith("trace_")


def test_dispatcher_passes_model_cron_status_topic_to_tool() -> None:
    import intent_tool_router as router
    import harness_dispatcher
    from harness_intent_agent import IntentFrame
    from unittest.mock import patch

    registry = router.load_registry()
    frame = IntentFrame(
        conversation_mode="task",
        domain="cron",
        action="status",
        canonical_text="为什么公共频道的新闻停了？",
        context_refs=[],
        parameters={"topic": "news"},
        safety="readonly",
        result_contract={"type": "cron_status", "topic": "news"},
        tool_candidates=[{"tool_id": "openclaw.cron.status", "confidence": 0.96, "reason": "semantic status check"}],
        confidence=0.96,
        reason="semantic status check",
    )
    seen = {}

    def fake_run(_tool, args, _timeout):
        seen.update(args)
        return 0, "OpenClaw 定时任务状态\n主题：news"

    with tempfile.TemporaryDirectory() as tmp, patch.object(harness_dispatcher, "infer_intent_frame", return_value=frame), patch.object(router, "run_tool", side_effect=fake_run):
        result = router.handle(
            "为什么公共频道的新闻停了？",
            "discord_dm",
            "999666719356354610",
            "2026-05-20T00:00:00+09:00",
            registry_override=registry,
            kernel_root=Path(tmp) / "kernel",
            context="",
        )

    assert result.status == "ok"
    assert seen["topic"] == "news"


def test_dispatcher_passes_model_news_window_and_delivery_contract_to_tool() -> None:
    import intent_tool_router as router
    import harness_dispatcher
    from harness_intent_agent import IntentFrame
    from unittest.mock import patch

    registry = router.load_registry()
    frame = IntentFrame(
        conversation_mode="task",
        domain="news",
        action="run",
        canonical_text="补发新闻正式任务",
        context_refs=[],
        parameters={
            "time_window": {"start": "5/18 17:00", "end": "5/19 17:00"},
            "delivery_target": "public channel",
        },
        safety="readonly",
        result_contract={"type": "cron_ack", "delivery": "public channel"},
        tool_candidates=[{"tool_id": "openclaw.cron.run.news", "confidence": 0.96, "reason": "semantic formal news makeup"}],
        confidence=0.96,
        reason="semantic formal news makeup",
    )
    seen = {}

    def fake_run(_tool, args, _timeout):
        seen.update(args)
        return 0, json.dumps({"status": "success", "job_name": args["job_name"], "final_report": "已补发到公共频道。"}, ensure_ascii=False)

    with tempfile.TemporaryDirectory() as tmp, patch.object(harness_dispatcher, "infer_intent_frame", return_value=frame), patch.object(router, "run_tool", side_effect=fake_run):
        result = router.handle(
            "补发昨天17点到今天17点的新闻到公共频道",
            "discord_dm",
            "999666719356354610",
            "2026-05-20T00:00:00+09:00",
            registry_override=registry,
            kernel_root=Path(tmp) / "kernel",
            context="",
        )

    assert result.status == "ok"
    assert seen["job_name"] == "news-digest-jst-today"
    assert seen["news_window_start"] == "5/18 17:00"
    assert seen["news_window_end"] == "5/19 17:00"
    assert seen["public_delivery"] is True
