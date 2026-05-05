from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import harness_context
import harness_governance
import harness_observability
import harness_runtime
import verify_harness_registry


def test_harness_registry_verifies() -> None:
    assert verify_harness_registry.verify() == 0


def test_harness_task_envelope_uses_registered_subagent() -> None:
    envelope = harness_runtime.build_task_envelope(
        intent="timescar.reservation_cancel",
        assigned_agent="timescarWorker",
        source_channel="discord_dm",
        user_id="999666719356354610",
        required_permissions=["owner_dm_write"],
        context_refs=["timescar_trace"],
        result_contract="cancel and post-check reservation absence",
    )
    assert envelope.trace_id.startswith("trace_")
    assert envelope.task_id.startswith("task_")
    assert envelope.assigned_agent == "timescarWorker"
    assert "owner_dm_write" in envelope.required_permissions


def test_harness_context_keeps_cron_free_from_dm_context() -> None:
    bundle = harness_context.build_context_bundle(
        trace_id="trace_test",
        intent="news.cron_run",
        channel="cron",
        user_id="system",
        dm_context="this must not leak",
        include_business_context=False,
        include_registry=True,
    )
    assert bundle.dm_context == ""
    assert "openclaw.cron.run.news" in bundle.registry_summary


def test_harness_governance_blocks_public_write_tool() -> None:
    registry = json.loads((verify_harness_registry.REPO / "config" / "openclaw" / "intent_tools.json").read_text(encoding="utf-8"))
    tool = next(item for item in registry["tools"] if item["tool_id"] == "timescar.dm.cancel_next")
    denied = harness_governance.evaluate_tool_invocation(tool, channel="discord_public", user_id="999666719356354610")
    allowed = harness_governance.evaluate_tool_invocation(tool, channel="discord_dm", user_id="999666719356354610")
    assert not denied.allowed
    assert allowed.allowed


def test_harness_observability_writes_jsonl() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "tool.jsonl"
        written = harness_observability.record_tool_invocation(
            harness_observability.ToolInvocationRecord(
                trace_id="trace_test",
                task_id="task_test",
                tool_id="timescar.dm.query",
                owner_agent="timescarWorker",
                status="ok",
                latency_ms=12,
                result_summary="queried",
                permission_scope="owner_dm",
            ),
            path=path,
        )
        assert written == path
        payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        assert payload["trace_id"] == "trace_test"
        assert payload["owner_agent"] == "timescarWorker"


def test_run_tool_records_harness_invocation_log() -> None:
    import intent_tool_router as router

    tool = {
        "intent_id": "test.intent",
        "tool_id": "test.tool",
        "owner_agent": "toolWorker",
        "permission_scope": "owner_dm",
        "entrypoint": "scripts/openclaw/intent_tool_router.py",
        "args_schema": {"mode": "dm_text_timestamp"},
    }
    args = {"text": "hello", "message_timestamp": "2026-05-04T00:00:00+09:00", "force": False}
    completed = type("Completed", (), {"returncode": 0, "stdout": "业务结果\n", "stderr": ""})()
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "harness.jsonl"
        with patch.dict(router.os.environ, {"OPENCLAW_HARNESS_TOOL_INVOCATION_LOG": str(log)}), patch.object(
            router.subprocess, "run", return_value=completed
        ):
            code, output = router.run_tool(tool, args, 10)
        assert code == 0
        assert output == "业务结果"
        payload = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
        assert payload["tool_id"] == "test.tool"
        assert payload["trace_id"].startswith("trace_")
