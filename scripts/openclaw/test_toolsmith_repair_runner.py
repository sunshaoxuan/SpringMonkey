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
            text="请查询小红书长记忆里 Frutteto 投稿记录",
            gap_type="registry_missing",
            readonly=True,
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
