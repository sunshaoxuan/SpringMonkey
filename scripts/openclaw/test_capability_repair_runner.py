from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import capability_repair_runner as runner


def blocker_response(kind: str, safety: str, confidence: float = 0.92) -> str:
    return json.dumps(
        {
            "intent_kind": "task",
            "blocker_kind": kind,
            "safety_class": safety,
            "confidence": confidence,
            "expected_capability_family": "test",
            "missing_condition": "test missing condition",
            "allowed_repair_action": "test repair action",
            "replay_policy": "allow_after_verified_promoted" if safety == "auto_safe_readonly" else "blocked_until_authorization",
            "reasoning_summary": f"test {kind}",
            "autonomy_allowed": False,
            "autonomy_boundary": "test",
        },
        ensure_ascii=False,
    )


def test_repair_runner_logs_verified_readonly_replay_event() -> None:
    tool = {
        "tool_id": "weather.dm.query",
        "entrypoint": "scripts/weather/handle_dm_weather_query.py",
        "write_operation": False,
        "verify_command": "python -m compileall -q scripts/weather/handle_dm_weather_query.py",
    }
    with tempfile.TemporaryDirectory() as tmp, patch("dm_capability_gap_runner.run_verify_command", return_value=(True, "ok")):
        root = Path(tmp) / "kernel"
        result = runner.run_repair(
            text="请查询明天东京天气和风况",
            channel="discord_dm",
            user_id="tester",
            stage="execute",
            reason="registered tool returned non-zero exit code 1",
            kernel_root=root,
            repo_root=Path(tmp),
            registry_tool=tool,
            blocker_model_caller=lambda _messages: blocker_response("readonly_tool_missing", "auto_safe_readonly"),
        )
        assert result.status == "verified"
        assert result.replay_allowed is True
        event_log = Path(result.event_log)
        events = [json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines()]
    assert events[-1]["stage"] == "execute"
    assert events[-1]["runner_status"] == "verified"
    assert events[-1]["replay_allowed"] is True


def test_repair_runner_blocks_write_replay() -> None:
    tool = {
        "tool_id": "timescar.dm.cancel_next",
        "entrypoint": "scripts/timescar/timescar_cancel_reservation.py",
        "write_operation": True,
    }
    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_repair(
            text="请取消这单订车",
            channel="discord_dm",
            user_id="tester",
            stage="execute",
            reason="registered tool missing verified submitter",
            kernel_root=Path(tmp) / "kernel",
            repo_root=Path(tmp),
            registry_tool=tool,
            blocker_model_caller=lambda _messages: blocker_response("write_operation_request", "requires_confirmation_or_credentials"),
        )
    assert result.status == "blocked"
    assert result.replay_allowed is False
    assert "not a verified read-only tool" in result.replay_reason or result.safety_class == "requires_confirmation_or_credentials"


def test_repair_runner_uses_llm_access_blocker_without_generating_readonly_helper() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_repair(
            text="我无法打开当前材料，需要对方批准后才能继续。",
            channel="discord_dm",
            user_id="tester",
            stage="binding",
            reason="no registered tool for IntentFrame domain/action: general/gap",
            kernel_root=Path(tmp) / "kernel",
            repo_root=Path(tmp),
            blocker_model_caller=lambda _messages: blocker_response(
                "access_or_approval_blocker",
                "requires_confirmation_or_credentials",
            ),
        )
        events = [json.loads(line) for line in Path(result.event_log).read_text(encoding="utf-8").splitlines()]

    assert result.status == "blocked"
    assert result.replay_allowed is False
    assert result.toolsmith_package["status"] == "blocked_requires_authorization"
    assert result.toolsmith_package["tool_id"] == "openclaw.authorization_required"
    assert result.toolsmith_package["tool_id"] != "memory.generated_readonly"
    assert events[-1]["llm_blocker_kind"] == "access_or_approval_blocker"
    assert events[-1]["missing_condition"] == "test missing condition"


def test_repair_runner_low_confidence_llm_blocks_helper_generation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_repair(
            text="处理一下这个问题",
            channel="discord_dm",
            user_id="tester",
            stage="binding",
            reason="unclear tool binding",
            kernel_root=Path(tmp) / "kernel",
            repo_root=Path(tmp),
            blocker_model_caller=lambda _messages: blocker_response(
                "readonly_tool_missing",
                "auto_safe_readonly",
                confidence=0.2,
            ),
        )

    assert result.status == "blocked"
    assert result.replay_allowed is False
    assert result.toolsmith_package["status"] == "blocked_requires_authorization"
    assert result.toolsmith_package["gap_type"] == "permission_missing"


def test_repair_runner_allows_llm_approved_internal_autonomy() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        (repo / "config" / "openclaw").mkdir(parents=True)
        (repo / "scripts" / "openclaw").mkdir(parents=True)
        (repo / "config" / "openclaw" / "intent_tools.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "tools": [
                        {
                            "tool_id": "openclaw.self_evolution.status",
                            "intent_id": "openclaw.self_evolution.status",
                            "entrypoint": "scripts/openclaw/self_evolution_status.py",
                            "write_operation": False,
                            "domain": "self",
                            "actions": ["status"],
                            "args_schema": {"mode": "self_evolution_status"},
                            "input_schema": {"type": "none"},
                            "output_schema": {"type": "plain_text_business_result"},
                            "permission": "owner_dm",
                            "permission_scope": "owner_dm_readonly",
                            "safety": "readonly",
                            "invocation_log_policy": "harness_tool_invocation_jsonl",
                            "failure_policy": "reply_failure_and_record_gap",
                            "reply_policy": "tool_stdout",
                            "verify_command": "python -m compileall -q scripts/openclaw/self_evolution_status.py",
                        }
                    ],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        with patch("toolsmith_repair_runner.run_command", return_value=(True, "ok")):
            result = runner.run_repair(
                text="请修复你自己的内部绑定并重试原任务",
                channel="discord_dm",
                user_id="tester",
                stage="binding",
                reason="no registered internal repair tool",
                kernel_root=Path(tmp) / "kernel",
                repo_root=repo,
                blocker_model_caller=lambda _messages: json.dumps(
                    {
                        "intent_kind": "self_improvement",
                        "blocker_kind": "access_or_approval_blocker",
                        "safety_class": "auto_safe_readonly",
                        "confidence": 0.94,
                        "expected_capability_family": "self_repair",
                        "missing_condition": "internal access path is missing but no external approval is required",
                        "allowed_repair_action": "autonomous_internal_repair",
                        "replay_policy": "allow_after_verified_promoted",
                        "reasoning_summary": "Internal self-improvement repair is allowed within privacy and rights boundaries.",
                        "autonomy_allowed": True,
                        "autonomy_boundary": "low_risk_internal_self_improvement",
                    },
                    ensure_ascii=False,
                ),
            )
        events = [json.loads(line) for line in Path(result.event_log).read_text(encoding="utf-8").splitlines()]

    assert result.status == "promoted"
    assert result.safety_class == "auto_safe_readonly"
    assert result.replay_allowed is True
    assert result.toolsmith_package["status"] == "promoted"
    assert result.toolsmith_package["tool_id"] != "openclaw.authorization_required"
    assert result.toolsmith_package["registry_patch"]["implementation_status"] == "ready"
    assert result.toolsmith_package["semantic_source"] == "openclaw.self_evolution.status"
    assert events[-1]["autonomy_allowed"] is True
    assert events[-1]["allowed_repair_action"] == "autonomous_internal_repair"


def test_repair_runner_does_not_bind_llm_classified_new_gap_to_legacy_weather_tool() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        (repo / "config" / "openclaw").mkdir(parents=True)
        (repo / "scripts" / "openclaw").mkdir(parents=True)
        (repo / "config" / "openclaw" / "intent_tools.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "tools": [
                        {
                            "tool_id": "weather.dm.query",
                            "intent_id": "weather.dm.query",
                            "entrypoint": "scripts/weather/handle_dm_weather_query.py",
                            "write_operation": False,
                            "domain": "weather",
                            "actions": ["query"],
                            "args_schema": {"mode": "dm_text_timestamp"},
                            "input_schema": {"type": "dm_text_timestamp"},
                            "output_schema": {"type": "plain_text_business_result"},
                            "permission": "owner_dm",
                            "permission_scope": "owner_dm",
                            "safety": "readonly",
                            "invocation_log_policy": "harness_tool_invocation_jsonl",
                            "failure_policy": "reply_failure_and_record_gap",
                            "reply_policy": "tool_stdout",
                            "verify_command": "python -m compileall -q scripts/weather/handle_dm_weather_query.py",
                        }
                    ],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        with patch("toolsmith_repair_runner.run_command", return_value=(True, "ok")):
            result = runner.run_repair(
                text="修改每日公共频道天气预报为图片形式，先在私聊测试，批准后再替换公共任务。",
                channel="discord_dm",
                user_id="tester",
                stage="binding",
                reason="no registered tool for weather image cron rollout",
                kernel_root=Path(tmp) / "kernel",
                repo_root=repo,
                blocker_model_caller=lambda _messages: json.dumps(
                    {
                        "intent_kind": "weather_image_cron_self_improvement",
                        "blocker_kind": "write_operation_request",
                        "safety_class": "auto_safe_readonly",
                        "confidence": 0.92,
                        "expected_capability_family": "weather.image_cron.rollout",
                        "missing_condition": "new image weather cron capability, DM test only before approval",
                        "allowed_repair_action": "autonomous_internal_repair",
                        "replay_policy": "allow_after_verified_promoted",
                        "reasoning_summary": "Internal implementation is allowed, public posting remains approval gated.",
                        "autonomy_allowed": True,
                        "autonomy_boundary": "dm_test_only_until_owner_approval",
                    },
                    ensure_ascii=False,
                ),
            )

    assert result.registry_tool is None or result.registry_tool.get("tool_id") != "weather.dm.query"
    assert result.status == "planned"
    assert result.toolsmith_package["status"] == "planned"
    assert result.toolsmith_package["tool_id"] != "weather.dm.query"
    assert result.toolsmith_package["registry_patch"] == {}
    assert result.replay_allowed is False


def test_repair_runner_records_toolsmith_package_for_unverified_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_repair(
            text="请帮我做一个新的只读查询",
            channel="discord_dm",
            user_id="tester",
            stage="binding",
            reason="no registered tool for readonly lookup",
            kernel_root=Path(tmp) / "kernel",
            repo_root=Path(tmp),
            forced_safety_class="auto_safe_readonly",
            forced_safety_reason="test readonly gap",
        )
        events = [json.loads(line) for line in Path(result.event_log).read_text(encoding="utf-8").splitlines()]
    assert result.status in {"generated", "verified"}
    assert events[-1]["resolved_by"]
    assert events[-1]["resolved_by"]["replay_policy"] in {"verify_before_replay", "blocked_until_human_authorization"}


def test_repair_runner_reuses_same_gap_event_fingerprint() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "kernel"
        kwargs = {
            "text": "请帮我做一个新的只读查询",
            "channel": "discord_dm",
            "user_id": "tester",
            "stage": "binding",
            "reason": "no registered tool for readonly lookup",
            "kernel_root": root,
            "repo_root": Path(tmp),
            "forced_safety_class": "auto_safe_readonly",
            "forced_safety_reason": "test readonly gap",
        }
        first = runner.run_repair(**kwargs)
        second = runner.run_repair(**kwargs)
        events = [json.loads(line) for line in Path(second.event_log).read_text(encoding="utf-8").splitlines()]

    assert first.toolsmith_package["package_id"] == second.toolsmith_package["package_id"]
    assert len(events) == 1
    assert events[0]["repair_fingerprint"]


def test_repair_runner_deploy_readonly_requires_deployed_package() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        (repo / "config" / "openclaw").mkdir(parents=True)
        (repo / "scripts" / "openclaw").mkdir(parents=True)
        (repo / "config" / "openclaw" / "intent_tools.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "tools": [
                        {
                            "tool_id": "openclaw.self_evolution.status",
                            "entrypoint": "scripts/openclaw/self_evolution_status.py",
                            "write_operation": False,
                            "domain": "self",
                            "actions": ["status"],
                            "input_schema": {"type": "none"},
                            "output_schema": {"type": "plain_text_business_result"},
                            "permission_scope": "owner_dm_readonly",
                            "safety": "readonly",
                        }
                    ],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        with patch("toolsmith_repair_runner.run_command", return_value=(True, "ok")):
            result = runner.run_repair(
                text="检查修复包状态",
                channel="discord_dm",
                user_id="tester",
                stage="binding",
                reason="no registered tool for readonly self evolution package status",
                kernel_root=Path(tmp) / "kernel",
                repo_root=repo,
                forced_safety_class="auto_safe_readonly",
                forced_safety_reason="test readonly gap",
                semantic=True,
                deploy_readonly=True,
            )
        events = [json.loads(line) for line in Path(result.event_log).read_text(encoding="utf-8").splitlines()]

    assert result.status == "deployed"
    assert result.replay_allowed is True
    assert events[-1]["resolved_by"]["status"] == "deployed"
    assert events[-1]["resolved_by"]["deployment_status"] == "git_deploy_requested"
