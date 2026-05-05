from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import harness_context


def test_latest_invocation_context_includes_recent_tool_summary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        log = workspace / "var" / "harness_tool_invocations.jsonl"
        log.parent.mkdir(parents=True)
        log.write_text(
            json.dumps(
                {
                    "tool_id": "timescar.dm.query",
                    "trace_id": "trace_old",
                    "input_summary": "查询未来一个月的 TimesCar 订车记录",
                    "result_summary": "TimesCar 预约查询结果\n范围：2026-05-05 至 2026-06-04",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        with patch.object(harness_context, "WORKSPACE", workspace):
            got = harness_context.latest_invocation_context()
    assert "timescar.dm.query" in got
    assert "trace_old" in got
    assert "未来一个月" in got


def test_context_prompt_includes_recent_invocations_for_dm() -> None:
    bundle = harness_context.HarnessContextBundle(
        trace_id="trace_test",
        intent="dm.event",
        channel="discord_dm",
        user_id="999666719356354610",
        dm_context="",
        business_context="",
        registry_summary="[]",
        recent_invocations='{"tool_id":"timescar.dm.query"}',
        memory_refs=[],
        rag_refs=[],
    )
    prompt = harness_context.context_to_prompt(bundle)
    assert "Recent tool invocations:" in prompt
    assert "timescar.dm.query" in prompt
