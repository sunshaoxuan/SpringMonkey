#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


CASES = [
    ("execution_blocked", "no response generated after direct task execution"),
    ("runtime_timeout", "timeout while waiting for first response"),
    ("tool_missing", "missing tool for direct visibility watchdog"),
]


def run_case(repo_root: Path, expected_category: str, observation: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="agent_society_gap_test_") as tmp:
        root = Path(tmp)
        cmd = [
            sys.executable,
            str(repo_root / "scripts" / "openclaw" / "agent_society_runtime_record_gap.py"),
            "--root",
            str(root),
            "--repo-root",
            str(repo_root),
            "--channel",
            "line",
            "--user-id",
            "tester",
            "--prompt",
            "please handle the direct task and report back",
            "--observation",
            observation,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        payload = json.loads(result.stdout)
        if payload["gap_category"] != expected_category:
            raise AssertionError(f"expected category {expected_category}, got {payload['gap_category']}")
        helper = payload.get("helper")
        if not helper:
            raise AssertionError(f"expected helper payload for {expected_category}")
        if helper["status"] != "promoted":
            raise AssertionError(f"expected promoted helper for {expected_category}, got {helper['status']}")
        helper_path = repo_root.joinpath(*helper["entrypoint"].split("/"))
        helper_run = subprocess.run(
            [
                sys.executable,
                str(helper_path),
                "--repo-root",
                str(repo_root),
                "--observation",
                observation,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        helper_output = json.loads(helper_run.stdout)
        if helper_output.get("status") != "ready":
            raise AssertionError(f"expected ready helper output for {expected_category}, got {helper_output.get('status')}")
        return {
            "expected_category": expected_category,
            "helper_name": helper["name"],
            "helper_status": helper["status"],
            "helper_category": helper_output.get("category"),
            "check_count": len(helper_output.get("checks", [])),
            "action_count": len(helper_output.get("suggested_actions", [])),
        }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    rows = [run_case(repo_root, expected_category, observation) for expected_category, observation in CASES]
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
