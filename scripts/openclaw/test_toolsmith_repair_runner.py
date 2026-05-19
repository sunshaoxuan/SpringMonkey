from __future__ import annotations

import tempfile
import json
import subprocess
import sys
from unittest.mock import patch
from pathlib import Path

import toolsmith_repair_runner as runner


def write_registry(repo: Path, tools: list[dict]) -> None:
    (repo / "config" / "openclaw").mkdir(parents=True)
    (repo / "config" / "openclaw" / "intent_tools.json").write_text(
        json.dumps({"schema_version": 1, "tools": tools}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def memory_reference_tool() -> dict:
    return {
        "intent_id": "memory.curator.xhs",
        "tool_id": "memory.curator.xhs",
        "owner_agent": "memoryWorker",
        "entrypoint": "scripts/openclaw/memory_curator_tool.py",
        "args_schema": {"mode": "memory_curator", "topic": "xhs"},
        "permission": "owner_dm",
        "permission_scope": "owner_dm_readonly",
        "write_operation": False,
        "input_schema": {"type": "fixed_memory_curator"},
        "output_schema": {"type": "plain_text_business_result", "requires_trace": True},
        "invocation_log_policy": "harness_tool_invocation_jsonl",
        "failure_policy": "reply_failure_and_record_gap",
        "reply_policy": "tool_stdout",
        "domain": "memory",
        "actions": ["quality", "clean", "query"],
        "worker_agent": "memoryWorker",
        "input_contract": {"type": "fixed_memory_curator"},
        "output_contract": {"type": "plain_text_business_result"},
        "safety": "readonly",
    }


def test_toolsmith_generates_readonly_repair_package() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = runner.generate_repair_package(
            text="请查询公开天气信息",
            reason="no registered tool for weather lookup",
            safety_class="auto_safe_readonly",
            kernel_root=root / "kernel",
            repo_root=root / "repo",
        )
    assert package.status == "generated"
    assert package.write_operation is False
    assert package.permission_scope == "owner_dm_readonly"
    assert package.replay_policy == "verify_before_replay"
    assert package.registry_patch["tool_id"] == package.tool_id
    assert package.verify_command
    assert len(package.files) >= 3
    assert package.fingerprint


def test_toolsmith_blocks_write_repair_package() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = runner.generate_repair_package(
            text="请取消这单订车",
            reason="missing cancellation executor",
            safety_class="requires_confirmation_or_credentials",
            kernel_root=root / "kernel",
            repo_root=root / "repo",
            registry_tool={"tool_id": "timescar.dm.cancel_next", "entrypoint": "scripts/timescar/cancel.py", "write_operation": True},
        )
    assert package.status == "blocked_requires_authorization"
    assert package.write_operation is True
    assert package.replay_policy == "blocked_until_human_authorization"


def test_toolsmith_llm_access_blocker_creates_authorization_package_not_helper() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = runner.generate_repair_package(
            text="我看不到材料，需要批准后才能继续",
            reason="model classified access blocker",
            safety_class="requires_confirmation_or_credentials",
            kernel_root=root / "kernel",
            repo_root=root / "repo",
            llm_classification={
                "blocker_kind": "access_or_approval_blocker",
                "missing_condition": "external approval required",
                "allowed_repair_action": "request authorization and retry original task after access is granted",
            },
        )
        auth_file = Path(package.files[0])
        auth_payload = json.loads(auth_file.read_text(encoding="utf-8"))

    assert package.status == "blocked_requires_authorization"
    assert package.gap_type == "permission_missing"
    assert package.tool_id == "openclaw.authorization_required"
    assert package.files == [str(auth_file)]
    assert auth_payload["llm_classification"]["blocker_kind"] == "access_or_approval_blocker"


def test_toolsmith_llm_autonomy_allowed_access_blocker_can_generate_helper() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = runner.generate_repair_package(
            text="请修复内部自演进状态读取",
            reason="model classified low-risk internal repair",
            safety_class="auto_safe_readonly",
            kernel_root=root / "kernel",
            repo_root=root / "repo",
            llm_classification={
                "blocker_kind": "access_or_approval_blocker",
                "allowed_repair_action": "autonomous_internal_repair",
                "autonomy_allowed": True,
            },
        )

    assert package.status == "generated"
    assert package.write_operation is False
    assert package.tool_id != "openclaw.authorization_required"
    assert package.registry_patch["write_operation"] is False


def test_toolsmith_write_request_internal_autonomy_creates_plan_not_generic_helper() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = runner.generate_repair_package(
            text="修改每日公共频道天气预报为图片形式，先在私聊测试，批准后再替换公共任务。",
            reason="missing image weather cron rollout capability",
            safety_class="auto_safe_readonly",
            kernel_root=root / "kernel",
            repo_root=root / "repo",
            semantic=True,
            llm_classification={
                "blocker_kind": "write_operation_request",
                "allowed_repair_action": "autonomous_internal_repair",
                "autonomy_allowed": True,
                "missing_condition": "new image cron rollout implementation",
            },
        )
        plan = json.loads(Path(package.files[0]).read_text(encoding="utf-8"))

    assert package.status == "planned"
    assert package.tool_id.startswith("openclaw.repair_plan.")
    assert package.registry_patch == {}
    assert package.files[0].endswith("domain_implementation_required.json")
    assert plan["implementation_required"] is True
    assert "do not promote a generic helper" in plan["next_step"]


def test_toolsmith_write_request_internal_plan_does_not_reuse_stale_generated_package() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        kernel_root = root / "kernel"
        stale = runner.generate_repair_package(
            text="修改每日公共频道天气预报为图片形式，先在私聊测试，批准后再替换公共任务。",
            reason="missing weather image helper",
            safety_class="auto_safe_readonly",
            kernel_root=kernel_root,
            repo_root=root / "repo",
            semantic=True,
        )
        planned = runner.generate_repair_package(
            text="修改每日公共频道天气预报为图片形式，先在私聊测试，批准后再替换公共任务。",
            reason="missing weather image helper",
            safety_class="auto_safe_readonly",
            kernel_root=kernel_root,
            repo_root=root / "repo",
            semantic=True,
            llm_classification={
                "blocker_kind": "write_operation_request",
                "allowed_repair_action": "autonomous_internal_repair",
                "autonomy_allowed": True,
                "expected_capability_family": "weather.image_cron.rollout",
            },
        )

    assert stale.status == "generated"
    assert planned.status == "planned"
    assert planned.tool_id.startswith("openclaw.repair_plan.")
    assert planned.package_id != stale.package_id
    assert planned.registry_patch == {}


def test_toolsmith_registered_tool_regression_internal_autonomy_creates_plan_not_helper() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = runner.generate_repair_package(
            text="继续补齐内部自增益能力并验证",
            reason="intent model unavailable or invalid: ValueError: invalid action: repair",
            safety_class="auto_safe_readonly",
            kernel_root=root / "kernel",
            repo_root=root / "repo",
            semantic=True,
            llm_classification={
                "blocker_kind": "registered_tool_regression",
                "allowed_repair_action": "autonomous_internal_repair",
                "autonomy_allowed": True,
                "expected_capability_family": "openclaw.self_evolution.internal_repair",
            },
        )
        plan = json.loads(Path(package.files[0]).read_text(encoding="utf-8"))

    assert package.status == "planned"
    assert package.replay_policy == "blocked_until_domain_implementation"
    assert package.write_operation is True
    assert package.entrypoint == ""
    assert package.registry_patch == {}
    assert not any("generated_" in item for item in package.files)
    assert plan["implementation_required"] is True


def test_toolsmith_routes_internal_autonomy_to_self_reference() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        write_registry(
            repo,
            [
                {
                    "intent_id": "openclaw.self_evolution.status",
                    "tool_id": "openclaw.self_evolution.status",
                    "entrypoint": "scripts/openclaw/self_evolution_status.py",
                    "args_schema": {"mode": "self_evolution_status"},
                    "permission": "owner_dm",
                    "permission_scope": "owner_dm_readonly",
                    "write_operation": False,
                    "domain": "self",
                    "actions": ["status"],
                    "input_schema": {"type": "none"},
                    "output_schema": {"type": "plain_text_business_result"},
                    "invocation_log_policy": "harness_tool_invocation_jsonl",
                    "failure_policy": "reply_failure_and_record_gap",
                    "reply_policy": "tool_stdout",
                    "safety": "readonly",
                }
            ],
        )
        package = runner.generate_repair_package(
            text="请重新处理刚才那个被权限阻断的问题，修复自身能力、内部日志、仓库、工具、测试、注册表或远端验证。",
            reason="model classified low-risk internal repair",
            safety_class="auto_safe_readonly",
            kernel_root=root / "kernel",
            repo_root=repo,
            semantic=True,
            llm_classification={
                "blocker_kind": "tool_binding_gap",
                "allowed_repair_action": "autonomous_internal_repair",
                "autonomy_allowed": True,
                "expected_capability_family": "self.status.retry",
            },
        )

    assert package.registry_patch["implementation_status"] == "ready"
    assert package.registry_patch["domain"] == "self"
    assert "retry" in package.registry_patch["actions"]
    assert package.semantic_source == "openclaw.self_evolution.status"



def test_toolsmith_self_evolution_binding_regression_resolves_existing_registered_tool() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        write_registry(
            repo,
            [
                {
                    "intent_id": "openclaw.self_evolution.internal_repair",
                    "tool_id": "openclaw.self_evolution.internal_repair",
                    "entrypoint": "scripts/openclaw/self_evolution_internal_repair.py",
                    "permission_scope": "owner_dm_write",
                    "write_operation": True,
                    "domain": "self",
                    "actions": ["repair", "implement", "verify", "push"],
                    "capability_id": "openclaw.self_evolution.internal_repair",
                }
            ],
        )
        package = runner.generate_repair_package(
            text="那你检查一下能力代码是不是有什么问题，请你修好它。",
            reason="Registered self repair tool semantically matches code inspection, repair, private verification, and verifiable completion requirements.",
            safety_class="auto_safe_readonly",
            kernel_root=root / "kernel",
            repo_root=repo,
            semantic=True,
            llm_classification={
                "intent_kind": "internal_self_evolution_repair",
                "blocker_kind": "write_operation_request",
                "autonomy_allowed": True,
                "expected_capability_family": "openclaw.self_evolution.internal_repair",
                "allowed_repair_action": "repair_binding_or_route_to_registered_tool_openclaw.self_evolution.internal_repair_then_privately_verify",
            },
        )
        plan = json.loads(Path(package.files[0]).read_text(encoding="utf-8"))

    assert package.status == "planned"
    assert package.tool_id == "openclaw.repair_plan.openclaw_self_evolution_internal_repair"
    assert package.permission_scope == "owner_dm_write"
    assert package.entrypoint == "scripts/openclaw/self_evolution_internal_repair.py"
    assert package.registry_patch == {}
    assert not any("generated_" in item for item in package.files)
    assert plan["registry_tool"]["tool_id"] == "openclaw.self_evolution.internal_repair"
    assert plan["implementation_required"] is True


def test_toolsmith_verify_promote_falls_back_when_pytest_missing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        write_registry(repo, [memory_reference_tool()])
        package = runner.generate_repair_package(
            text="请查询小红书长记忆里 Frutteto 投稿记录",
            reason="no registered tool for readonly memory lookup",
            safety_class="auto_safe_readonly",
            kernel_root=root / "kernel",
            repo_root=repo,
            semantic=True,
            llm_classification={
                "blocker_kind": "readonly_tool_missing",
                "expected_capability_family": "memory.query",
            },
        )
        outputs = []

        def fake_run(command: str, _repo: Path) -> tuple[bool, str]:
            outputs.append(command)
            if "pytest" in command:
                return False, "/usr/local/bin/python: No module named pytest"
            if "generated_openclaw_generated_memory_query.py" in command and command.startswith("python "):
                return True, '{"status": "success", "result": "ok"}'
            return True, "ok"

        with patch("toolsmith_repair_runner.run_command", side_effect=fake_run):
            promoted = runner.verify_and_promote_package(package, kernel_root=root / "kernel", repo_root=repo)

    assert promoted.status == "promoted"
    assert "pytest unavailable; used generated helper contract fallback" in promoted.verify_output
    assert any("python scripts/openclaw/helpers/generated_openclaw_generated_memory_query.py" in item for item in outputs)


def test_toolsmith_promotes_readonly_package_after_verify() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        (repo / "config" / "openclaw").mkdir(parents=True)
        (repo / "scripts" / "openclaw").mkdir(parents=True)
        (repo / "config" / "openclaw" / "intent_tools.json").write_text(
            '{"schema_version": 1, "tools": []}\n',
            encoding="utf-8",
        )
        package = runner.generate_repair_package(
            text="请查询公开天气信息",
            reason="no registered tool for weather lookup",
            safety_class="auto_safe_readonly",
            kernel_root=root / "kernel",
            repo_root=repo,
        )
        package.registry_patch["implementation_status"] = "ready"
        with patch("toolsmith_repair_runner.run_command", return_value=(True, "ok")):
            promoted = runner.verify_and_promote_package(package, kernel_root=root / "kernel", repo_root=repo)
        helper_exists = (repo / promoted.entrypoint).is_file()
        registry_text = (repo / "config" / "openclaw" / "intent_tools.json").read_text(encoding="utf-8")
        helper_registry_exists = (root / "kernel" / "helper_registry.json").is_file()

    assert promoted.status == "promoted"
    assert helper_exists
    assert promoted.tool_id in registry_text
    assert helper_registry_exists


def test_toolsmith_refuses_to_overwrite_existing_registered_tool_without_explicit_replacement() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        write_registry(
            repo,
            [
                {
                    "intent_id": "weather.dm.query",
                    "tool_id": "weather.dm.query",
                    "entrypoint": "scripts/weather/handle_dm_weather_query.py",
                    "write_operation": False,
                    "domain": "weather",
                    "actions": ["query"],
                    "input_schema": {"type": "dm_text_timestamp"},
                    "output_schema": {"type": "plain_text_business_result"},
                    "permission": "owner_dm",
                    "permission_scope": "owner_dm",
                    "safety": "readonly",
                }
            ],
        )
        package = runner.generate_repair_package(
            text="修改天气预报能力",
            reason="new weather image cron capability missing",
            safety_class="auto_safe_readonly",
            kernel_root=root / "kernel",
            repo_root=repo,
            registry_tool={
                "tool_id": "weather.dm.query",
                "entrypoint": "scripts/weather/handle_dm_weather_query.py",
                "write_operation": False,
            },
            semantic=True,
        )
        package.registry_patch["implementation_status"] = "ready"
        promoted = runner.verify_and_promote_package(package, kernel_root=root / "kernel", repo_root=repo)

    assert promoted.status == "generated"
    assert "would overwrite an existing registered tool" in promoted.verify_output



def test_toolsmith_weather_formal_cron_public_rollout_routes_to_self_evolution_repair() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        write_registry(
            repo,
            [
                {
                    "intent_id": "openclaw.self_evolution.internal_repair",
                    "tool_id": "openclaw.self_evolution.internal_repair",
                    "entrypoint": "scripts/openclaw/self_evolution_internal_repair.py",
                    "write_operation": True,
                    "permission_scope": "owner_dm_write",
                    "capability_id": "openclaw.self_evolution.internal_repair",
                    "domain": "self",
                    "actions": ["repair", "implement", "verify"],
                },
                {
                    "intent_id": "weather.cron_run",
                    "tool_id": "openclaw.cron.run.weather",
                    "entrypoint": "scripts/openclaw/run_job_by_name.py",
                    "write_operation": False,
                    "permission_scope": "owner_dm",
                    "domain": "weather",
                    "actions": ["run"],
                },
            ],
        )
        package = runner.generate_repair_package(
            text="替换掉正式的每日7点的天气预报任务，投放给公共频道",
            reason="registered weather run tool cannot modify the formal cron workflow; public delivery must remain gated",
            safety_class="auto_safe_readonly",
            kernel_root=root / "kernel",
            repo_root=repo,
            semantic=True,
            llm_classification={
                "intent_kind": "update_formal_weather_cron_and_request_public_delivery",
                "blocker_kind": "write_operation_request",
                "expected_capability_family": "openclaw.self_evolution.internal_repair",
                "allowed_repair_action": "autonomous_internal_repair",
                "autonomy_allowed": True,
            },
        )
        state = json.loads(Path(package.files[0]).read_text(encoding="utf-8"))

    assert package.status == "planned"
    assert package.tool_id == "openclaw.repair_plan.openclaw_self_evolution_internal_repair"
    assert state["registry_tool"]["tool_id"] == "openclaw.self_evolution.internal_repair"
    assert state["implementation_required"] is True


def test_toolsmith_defers_promotion_without_formal_registry() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = runner.generate_repair_package(
            text="请查询公开天气信息",
            reason="no registered tool for weather lookup",
            safety_class="auto_safe_readonly",
            kernel_root=root / "kernel",
            repo_root=root / "repo",
        )
        promoted = runner.verify_and_promote_package(package, kernel_root=root / "kernel", repo_root=root / "repo")

    assert promoted.status == "generated"
    assert "candidate draft" in promoted.verify_output


def test_toolsmith_selects_reference_tool_from_registry() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        write_registry(repo, [memory_reference_tool()])
        reference = runner.find_reference_tool(
            repo,
            gap_type="registry_missing",
            readonly=True,
            llm_classification={"expected_capability_family": "memory.query"},
        )

    assert reference
    assert reference["tool_id"] == "memory.curator.xhs"


def test_toolsmith_generates_semantic_ready_helper_not_draft() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        write_registry(repo, [memory_reference_tool()])
        package = runner.generate_repair_package(
            text="请查询小红书长记忆里 Frutteto 投稿记录",
            reason="no registered tool for readonly memory lookup",
            safety_class="auto_safe_readonly",
            kernel_root=root / "kernel",
            repo_root=repo,
            semantic=True,
            llm_classification={
                "blocker_kind": "readonly_tool_missing",
                "expected_capability_family": "memory.query",
            },
        )
        helper = Path(package.files[0])
        proc = subprocess.run(
            [sys.executable, str(helper), "--text", "检查自演进状态"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=True,
        )
        payload = json.loads(proc.stdout)

    assert package.status == "generated"
    assert package.registry_patch["implementation_status"] == "ready"
    assert package.registry_patch["semantic_reference_tool_id"] == "memory.curator.xhs"
    assert package.semantic_source == "memory.curator.xhs"
    assert payload["status"] == "success"
    assert "draft" not in proc.stdout.lower()


def test_toolsmith_marks_promoted_readonly_package_deployed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = runner.generate_repair_package(
            text="请查询公开天气信息",
            reason="no registered tool for weather lookup",
            safety_class="auto_safe_readonly",
            kernel_root=root / "kernel",
            repo_root=root / "repo",
        )
        package.status = "promoted"
        deployed = runner.mark_deployed(package)

    assert deployed.status == "deployed"
    assert deployed.deployment_status == "git_deploy_requested"
