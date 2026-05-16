from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def test_self_evolution_status_honors_superseded_package_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        kernel = Path(tmp) / "kernel"
        package_dir = kernel / "toolsmith_packages" / "repair_bad"
        package_dir.mkdir(parents=True)
        (package_dir / "package_state.json").write_text(
            json.dumps({"status": "superseded", "deployment_status": "superseded_by_test"}, ensure_ascii=False),
            encoding="utf-8",
        )
        (kernel / "capability_gap_events.jsonl").write_text(
            json.dumps(
                {
                    "stage": "binding",
                    "runner_status": "promoted",
                    "safety_class": "auto_safe_readonly",
                    "replay_allowed": True,
                    "tool_id": "openclaw.generated.registry_missing",
                    "resolved_by": {"package_id": "repair_bad", "status": "promoted"},
                    "repair_fingerprint": "abc",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        proc = subprocess.run(
            [sys.executable, "scripts/openclaw/self_evolution_status.py", "--kernel-root", str(kernel)],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=True,
        )

    assert "status=superseded" not in proc.stdout
    assert "能力缺口事件：0 条最近有效记录" in proc.stdout
    assert "未解决缺口" not in proc.stdout
