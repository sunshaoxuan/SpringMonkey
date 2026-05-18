#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import intent_tool_router as router


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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print(f"{Path(__file__).name}: ok")
