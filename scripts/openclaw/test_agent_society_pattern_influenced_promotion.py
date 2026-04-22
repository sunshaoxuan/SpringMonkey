#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run_gap(repo_root: Path, root: Path, observation: str) -> dict[str, object]:
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
    return json.loads(result.stdout)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="agent_society_pattern_promotion_") as tmp:
        root = Path(tmp)
        observation = "runtime bundle patch anchor drift detected in current bundle"
        runs = [run_gap(repo_root, root, observation) for _ in range(3)]
        statuses = [run["pattern"]["status"] for run in runs]
        helper_statuses = [run["helper"]["status"] for run in runs]
        helper_names = [run["helper"]["name"] for run in runs]

        payload = {
            "pattern_statuses": statuses,
            "helper_statuses": helper_statuses,
            "helper_names": helper_names,
            "final_pattern": runs[-1]["pattern"],
        }

        if statuses != ["candidate", "emerging", "learned"]:
            raise AssertionError(f"unexpected pattern status progression: {statuses}")
        if helper_statuses[-1] != "promoted":
            raise AssertionError(f"expected learned-pattern promotion on third run, got {helper_statuses[-1]}")
        if not all(name == helper_names[0] for name in helper_names):
            raise AssertionError(f"expected stable helper naming across learned pattern, got {helper_names}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
