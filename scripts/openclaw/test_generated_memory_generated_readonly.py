from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_generated_semantic_helper_runs_with_business_contract() -> None:
    repo = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, str(repo / "scripts/openclaw/helpers/generated_memory_generated_readonly.py"), "--text", "检查自演进状态"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["status"] == "success"
    assert payload["tool_id"]
    assert payload["result"]
    assert "draft" not in proc.stdout.lower()
    assert payload["trace"]["semantic_helper"] is True
