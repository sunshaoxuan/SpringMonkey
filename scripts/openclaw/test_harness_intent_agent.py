from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import harness_intent_agent as agent
from model_fallback_client import ChatEndpoint


def load_registry() -> dict:
    return json.loads((Path(__file__).resolve().parents[2] / "config" / "openclaw" / "intent_tools.json").read_text(encoding="utf-8"))


def model_reply(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def test_intent_frame_timescar_month_query() -> None:
    with tempfile.TemporaryDirectory() as tmp, patch.dict(agent.os.environ, {"OPENCLAW_HARNESS_MODEL_CALL_LOG": str(Path(tmp) / "model.jsonl")}):
        frame = agent.infer_intent_frame(
            "帮我查未来一个月的订车记录",
            context="",
            registry=load_registry(),
            model_caller=lambda _messages: model_reply(
                {
                    "conversation_mode": "task",
                    "domain": "timescar",
                    "action": "query",
                    "canonical_text": "查询 TimesCar 预约 未来一个月",
                    "context_refs": [],
                    "parameters": {"duration_hours": 720, "offset_hours": 0, "relation": "within"},
                    "safety": "readonly",
                    "result_contract": {"type": "timescar_query_range"},
                    "tool_candidates": [{"tool_id": "timescar.dm.query", "confidence": 0.98, "reason": "registered query capability"}],
                    "confidence": 0.98,
                    "reason": "TimesCar reservation query",
                }
            ),
        )
    assert frame.domain == "timescar"
    assert frame.action == "query"
    assert frame.parameters["duration_hours"] == 720
    assert frame.parameters["offset_hours"] == 0


def test_long_task_status_uses_semantic_contract_frame() -> None:
    frame = agent.infer_intent_frame(
        "检查长任务状态",
        context="",
        registry=load_registry(),
        model_caller=lambda _messages: model_reply(
            {
                "conversation_mode": "task",
                "domain": "cron",
                "action": "status",
                "canonical_text": "检查最近长任务生命周期状态。",
                "context_refs": [],
                "parameters": {"subject": "long_task"},
                "safety": "readonly",
                "result_contract": {"type": "long_task_status"},
                "tool_candidates": [{"tool_id": "openclaw.long_task.status", "confidence": 0.98, "reason": "semantic ToolContract match"}],
                "confidence": 0.98,
                "reason": "long task status request",
            }
        ),
    )

    assert frame.domain == "cron"
    assert frame.action == "status"
    assert frame.tool_candidates[0]["tool_id"] == "openclaw.long_task.status"
    assert frame.source == "model"


def test_intent_prompt_requires_boundary_split_for_self_improvement_public_release() -> None:
    messages = agent.build_prompt(
        "检查能力增强进度，没做完就做完，落实能力后推仓库，在私人频道测试通过后再发布到公共频道。",
        context="",
        registry=load_registry(),
    )
    system = messages[0]["content"]

    assert "split the boundary semantically" in system
    assert "git push" in system
    assert "public-channel replacement" in system
    assert "Do not reject the whole request as boundary-unclear" in system


def test_self_evolution_repair_action_is_valid_and_binds_contract() -> None:
    frame = agent.infer_intent_frame(
        "继续补齐刚才失败的内部自增益能力，真实修改仓库并验证。",
        context="",
        registry=load_registry(),
        model_caller=lambda _messages: model_reply(
            {
                "conversation_mode": "task",
                "domain": "self",
                "action": "repair",
                "canonical_text": "继续执行内部自增益修复，修改仓库、运行验证并保持公共发布审批门。",
                "context_refs": [],
                "parameters": {"approval_gate": "public_release"},
                "safety": "write",
                "result_contract": {"type": "self_evolution_repair_result"},
                "tool_candidates": [
                    {
                        "tool_id": "openclaw.self_evolution.internal_repair",
                        "confidence": 0.98,
                        "reason": "semantic self-evolution repair contract",
                    }
                ],
                "confidence": 0.98,
                "reason": "owner-controlled internal repair",
            }
        ),
    )

    assert frame.domain == "self"
    assert frame.action == "repair"
    assert frame.tool_candidates[0]["tool_id"] == "openclaw.self_evolution.internal_repair"


def test_intent_prompt_lists_self_evolution_repair_actions() -> None:
    messages = agent.build_prompt("继续补齐内部自增益能力", context="", registry=load_registry())
    system = messages[0]["content"]

    assert "repair|implement|verify|push" in system
    assert "openclaw.self_evolution.internal_repair" in system


def test_intent_prompt_requires_structured_container_types() -> None:
    system = agent.build_prompt("你好", context="", registry=load_registry())[0]["content"]

    assert "context_refs and tool_candidates must be JSON arrays" in system
    assert "parameters and result_contract must be JSON objects" in system
    assert "never use null or a string" in system


def test_intent_model_has_no_default_22545_fallback(monkeypatch) -> None:
    for key in (
        "OPENCLAW_INTENT_FALLBACK_BASE_URL",
        "OPENCLAW_INTENT_FALLBACK_MODELS",
        "OPENCLAW_OLLAMA_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)

    assert agent.intent_model_fallback_configs() == []


def test_intent_model_uses_only_explicit_fallback(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_INTENT_FALLBACK_BASE_URL", "http://fallback.example/v1")
    monkeypatch.setenv("OPENCLAW_INTENT_FALLBACK_MODELS", "gemini-pro-agent")
    monkeypatch.setenv("OPENCLAW_INTENT_FALLBACK_API_KEY", "test-key")

    assert agent.intent_model_fallback_configs() == [("http://fallback.example/v1", "test-key", "gemini-pro-agent")]


def test_intent_model_fallback_key_can_use_file(monkeypatch, tmp_path: Path) -> None:
    key_file = tmp_path / "fallback.key"
    key_file.write_text("file-key", encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_INTENT_FALLBACK_BASE_URL", "http://fallback.example/v1")
    monkeypatch.setenv("OPENCLAW_INTENT_FALLBACK_MODELS", "gemini-pro-agent")
    monkeypatch.delenv("OPENCLAW_INTENT_FALLBACK_API_KEY", raising=False)
    monkeypatch.setenv("OPENCLAW_INTENT_FALLBACK_API_KEY_FILE", str(key_file))

    assert agent.intent_model_fallback_configs() == [("http://fallback.example/v1", "file-key", "gemini-pro-agent")]


def test_intent_model_uses_longer_bounded_fallback_timeout(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_INTENT_FALLBACK_TIMEOUT_SECONDS", "180")
    assert agent.intent_model_fallback_timeout(30) == 180

    monkeypatch.setenv("OPENCLAW_INTENT_FALLBACK_TIMEOUT_SECONDS", "900")
    assert agent.intent_model_fallback_timeout(30) == 300
    assert agent.intent_model_fallback_timeout(600) == 300


def test_invalid_primary_intent_frame_uses_explicit_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENCLAW_HARNESS_MODEL_CALL_LOG", str(tmp_path / "model.jsonl"))
    monkeypatch.setenv("OPENCLAW_INTENT_FALLBACK_BASE_URL", "http://fallback.example/v1")
    monkeypatch.setenv("OPENCLAW_INTENT_FALLBACK_MODELS", "qwen-fallback")
    monkeypatch.setenv("OPENCLAW_INTENT_FALLBACK_API_KEY", "test-key")
    fallback_reply = model_reply(
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
        }
    )

    with patch.object(agent, "call_model", return_value=("not json", {"model": "primary"})), patch.object(
        agent, "chat_with_fallback", return_value=(fallback_reply, {"model": "qwen-fallback", "latency_ms": 12})
    ) as fallback_call:
        frame = agent.infer_intent_frame("你好", context="", registry=load_registry())

    assert frame.conversation_mode == "chat"
    fallback_call.assert_called_once()
    kwargs = fallback_call.call_args.kwargs
    assert kwargs["primary"] == ChatEndpoint(
        "openai_compatible", "http://fallback.example/v1", "qwen-fallback", "test-key"
    )
    assert kwargs["timeout"] == 180
    assert kwargs["allow_fallback"] is False
    log = json.loads((tmp_path / "model.jsonl").read_text(encoding="utf-8"))
    assert log["fallback_used"] is True
    assert log["model"] == "qwen-fallback"
    assert log["attempts"][0]["model"] == "primary"


def test_primary_transport_failure_uses_explicit_intent_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENCLAW_HARNESS_MODEL_CALL_LOG", str(tmp_path / "model.jsonl"))
    monkeypatch.setenv("OPENCLAW_INTENT_FALLBACK_BASE_URL", "http://fallback.example/v1")
    monkeypatch.setenv("OPENCLAW_INTENT_FALLBACK_MODELS", "qwen-fallback")
    fallback_reply = model_reply(
        {
            "conversation_mode": "chat",
            "domain": "general",
            "action": "chat",
            "canonical_text": "在。",
            "context_refs": [],
            "parameters": {},
            "safety": "readonly",
            "result_contract": {},
            "tool_candidates": [],
            "confidence": 0.99,
            "reason": "liveness",
        }
    )

    with patch.object(agent, "call_model", side_effect=RuntimeError("primary unavailable")), patch.object(
        agent, "chat_with_fallback", return_value=(fallback_reply, {"model": "qwen-fallback", "latency_ms": 10})
    ):
        frame = agent.infer_intent_frame("还活着吗", context="", registry=load_registry())

    assert frame.canonical_text == "在。"


def test_timescar_shift_window_uses_semantic_model_frame() -> None:
    frame = agent.infer_intent_frame(
        "请把马上开始的那单预订帮我往后整体延15分钟。",
        context="",
        registry=load_registry(),
        model_caller=lambda _messages: model_reply(
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
            }
        ),
    )

    assert frame.domain == "timescar"
    assert frame.action == "adjust"
    assert frame.tool_candidates[0]["tool_id"] == "timescar.dm.shift_window"


def test_timescar_tomorrow_relative_adjust_uses_semantic_model_frame() -> None:
    frame = agent.infer_intent_frame(
        "请把明天开始的 TimesCar 订车预约的开始时间往后延 24 小时，结束时间保持不变。",
        context="",
        registry=load_registry(),
        model_caller=lambda _messages: model_reply(
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
            }
        ),
    )

    assert frame.domain == "timescar"
    assert frame.action == "adjust"
    assert frame.tool_candidates[0]["tool_id"] == "timescar.dm.adjust_start"


def test_artifact_access_followup_is_model_routed_away_from_task_status() -> None:
    frame = agent.infer_intent_frame(
        "我需要查看刚才生成的 Google Docs，请给我文件查看权限。",
        context="Recent long task final report includes a Google Docs URL.",
        registry=load_registry(),
        model_caller=lambda _messages: model_reply(
            {
                "conversation_mode": "task",
                "domain": "artifact",
                "action": "access",
                "canonical_text": "为最近交付的 Google Docs 文件处理查看权限，不要重复报告生成任务成功。",
                "context_refs": [{"type": "recent_delivered_artifact", "selector": "latest_google_doc"}],
                "parameters": {"artifact_kind": "google_doc", "access_level": "viewer"},
                "safety": "write",
                "result_contract": {"type": "artifact_access_followup"},
                "tool_candidates": [{"tool_id": "openclaw.artifact.access_followup", "confidence": 0.98, "reason": "artifact access follow-up"}],
                "confidence": 0.98,
                "reason": "The user is asking for viewing permission, not job status.",
            }
        ),
    )

    assert frame.domain == "artifact"
    assert frame.action == "access"
    assert frame.tool_candidates[0]["tool_id"] == "openclaw.artifact.access_followup"


def test_artifact_update_followup_is_model_routed_to_update_tool() -> None:
    frame = agent.infer_intent_frame(
        "请给刚才生成的文档补充三张高清无水印图片并更新交付物。",
        context="Recent long task final report includes a Google Docs URL.",
        registry=load_registry(),
        model_caller=lambda _messages: model_reply(
            {
                "conversation_mode": "task",
                "domain": "artifact",
                "action": "update",
                "canonical_text": "为最近交付的 Google Docs 文件补充三张图片并更新交付物。",
                "context_refs": [{"type": "recent_delivered_artifact", "selector": "latest_google_doc"}],
                "parameters": {"artifact_kind": "google_doc", "image_count": 3},
                "safety": "write",
                "result_contract": {"type": "artifact_update_followup"},
                "tool_candidates": [{"tool_id": "openclaw.artifact.update_followup", "confidence": 0.98, "reason": "artifact update follow-up"}],
                "confidence": 0.98,
                "reason": "The user is asking to edit the delivered artifact, not to check task status.",
            }
        ),
    )

    assert frame.domain == "artifact"
    assert frame.action == "update"
    assert frame.tool_candidates[0]["tool_id"] == "openclaw.artifact.update_followup"


def test_intent_frame_normalizes_nested_time_range() -> None:
    frame = agent.validate_intent_frame(
        {
            "conversation_mode": "task",
            "domain": "timescar",
            "action": "query",
            "canonical_text": "查询未来一个月内的 TimesCar 订车记录。",
            "context_refs": [],
            "parameters": {"time_range": {"duration_hours": 720, "offset_hours": 0, "relation": "within"}},
            "safety": "readonly",
            "result_contract": {},
            "tool_candidates": [{"tool_id": "timescar.dm.query", "confidence": 0.98, "reason": "registered query capability"}],
            "confidence": 0.98,
            "reason": "TimesCar reservation query",
        }
    )
    assert frame.parameters["duration_hours"] == 720
    assert frame.parameters["offset_hours"] == 0
    assert frame.parameters["relation"] == "within"


def test_intent_frame_chat_has_no_tool() -> None:
    frame = agent.infer_intent_frame(
        "你好",
        context="",
        registry=load_registry(),
        model_caller=lambda _messages: model_reply(
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
            }
        ),
    )
    assert frame.conversation_mode == "chat"
    assert frame.tool_candidates == []


def test_intent_frame_web_research() -> None:
    frame = agent.infer_intent_frame(
        "帮我查一下 OpenClaw 最新版本",
        context="",
        registry=load_registry(),
        model_caller=lambda _messages: model_reply(
            {
                "conversation_mode": "task",
                "domain": "web",
                "action": "research",
                "canonical_text": "联网查询 OpenClaw 最新版本并用中文总结。",
                "context_refs": [],
                "parameters": {"freshness": "latest", "language": "zh-CN"},
                "safety": "readonly",
                "result_contract": {"type": "web_research"},
                "tool_candidates": [{"tool_id": "openclaw.web.research", "confidence": 0.97, "reason": "public web research"}],
                "confidence": 0.97,
                "reason": "public information query",
            }
        ),
    )
    assert frame.domain == "web"
    assert frame.action == "research"
    assert frame.tool_candidates[0]["tool_id"] == "openclaw.web.research"


def test_prompt_makes_model_choose_capability_not_business_keyword() -> None:
    messages = agent.build_prompt("我订的车可以提前多久订？", "", load_registry())
    system = messages[0]["content"]
    assert "Choose by semantic fit to ToolContract" in system
    assert "Never choose by business keyword matching" in system
    assert "public rules, policy" in system
    assert "not timescar gap" in system


def test_invalid_intent_frame_is_rejected() -> None:
    try:
        agent.validate_intent_frame({"conversation_mode": "task", "domain": "bad", "action": "query"})
        raise AssertionError("invalid domain should fail")
    except ValueError:
        pass


def test_incomplete_intent_frame_is_rejected() -> None:
    try:
        agent.validate_intent_frame({})
        raise AssertionError("incomplete frame should fail")
    except ValueError as exc:
        assert "missing required keys" in str(exc)


def test_malformed_tool_candidate_is_rejected() -> None:
    data = {
        "conversation_mode": "task",
        "domain": "web",
        "action": "research",
        "canonical_text": "查询当前信息。",
        "context_refs": [],
        "parameters": {},
        "safety": "readonly",
        "result_contract": {},
        "tool_candidates": ["openclaw.web.research"],
        "confidence": 0.9,
        "reason": "research",
    }
    try:
        agent.validate_intent_frame(data)
        raise AssertionError("malformed tool candidate should fail")
    except ValueError as exc:
        assert "tool_candidates entries" in str(exc)


def test_explicit_null_optional_containers_are_normalized() -> None:
    frame = agent.validate_intent_frame(
        {
            "conversation_mode": "chat",
            "domain": "general",
            "action": "chat",
            "canonical_text": "在。",
            "context_refs": None,
            "parameters": None,
            "safety": "readonly",
            "result_contract": None,
            "tool_candidates": None,
            "confidence": 0.9,
            "reason": "liveness",
        }
    )
    assert frame.context_refs == []
    assert frame.parameters == {}
    assert frame.result_contract == {}
    assert frame.tool_candidates == []


def test_extract_json_object_ignores_trailing_braces() -> None:
    assert agent.extract_json_object('{"domain":"general"} trailing } text') == {"domain": "general"}
