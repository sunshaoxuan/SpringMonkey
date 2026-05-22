#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import intent_tool_router as router
from harness_intent_agent import IntentFrame


def tool(push_default: bool = False):
    return {
        "entrypoint": "scripts/openclaw/self_evolution_internal_repair.py",
        "args_schema": {"mode": "self_evolution_internal_repair", "push": push_default, "dry_run": False},
    }


def test_extract_args_preserves_reason_package_and_user_push_request():
    text = '''implementation_run_id: impl_router
repo_root: /tmp/repo
失败原因：
This fits the registered internal_repair tool; public-channel release is explicitly excluded.

repair package：
{"files": ["/tmp/pkg/domain_implementation_required.json"]}

请运行验证并推仓库。'''
    args = router.extract_args(tool(), text, "2026-05-18T13:44:00+09:00")
    assert args["implementation_run_id"] == "impl_router"
    assert args["repo_root"] == "/tmp/repo"
    assert args["package_state"] == "/tmp/pkg/domain_implementation_required.json"
    assert args["push"] is True
    assert "registered internal_repair tool" in args["reason"]


def test_run_tool_passes_push_flag_for_internal_repair():
    captured = {}

    class Proc:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return Proc()

    args = {
        "text": "内部能力补齐并推仓库",
        "reason": "internal repair",
        "implementation_run_id": "impl_router",
        "repo_root": "/tmp/repo",
        "package_state": "/tmp/pkg.json",
        "push": True,
        "dry_run": False,
    }
    with patch.object(router.subprocess, "run", side_effect=fake_run):
        code, out = router.run_tool(tool(), args, timeout_seconds=30)
    assert code == 0 and out == "ok"
    cmd = captured["cmd"]
    assert "--push" in cmd
    assert cmd[cmd.index("--implementation-run-id") + 1] == "impl_router"
    assert cmd[cmd.index("--package-state") + 1] == "/tmp/pkg.json"
    joined = " ".join(cmd)
    assert "天气" not in joined and "weather" not in joined.lower()



def test_verify_repair_package_alias_binds_to_internal_repair_tool():
    frame = IntentFrame(
        conversation_mode="task",
        domain="self",
        action="verify",
        canonical_text="验证修复包 implementation_run_id: impl_alias",
        context_refs=[],
        parameters={},
        safety="readonly",
        result_contract={"type": "self_evolution_repair_result"},
        tool_candidates=[
            {
                "tool_id": "openclaw.repair_plan.openclaw_self_evolution_internal_repair",
                "confidence": 0.96,
                "reason": "semantic repair package verification alias",
            }
        ],
        confidence=0.96,
        reason="repair package verification maps to registered self-evolution verifier",
    )
    registry = {"tools": [dict(tool(), **{
        "tool_id": "openclaw.self_evolution.internal_repair",
        "intent_id": "openclaw.self_evolution.internal_repair",
        "domain": "self",
        "actions": ["repair", "implement", "verify", "push"],
        "readonly_actions": ["verify"],
        "tool_aliases": ["openclaw.repair_plan.openclaw_self_evolution_internal_repair"],
        "write_operation": True,
    })]}

    binding = router.bind_tool(frame, registry)
    review = router.review_intent_frame(frame, binding.tool, "验证你的修复包")

    assert binding.status == "bound"
    assert binding.tool and binding.tool["tool_id"] == "openclaw.self_evolution.internal_repair"
    assert review.passed is True

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print(f"{Path(__file__).name}: ok")
