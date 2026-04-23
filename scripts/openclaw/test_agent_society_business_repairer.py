#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from agent_society_helper_toolsmith import create_helper_tool


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="agent_society_business_repairer_") as tmp:
        sandbox_repo = Path(tmp) / "repo"
        sandbox_repo.mkdir(parents=True, exist_ok=True)
        for rel in [
            "scripts/openclaw/agent_society_runtime_record_gap.py",
            "scripts/openclaw/agent_society_helper_toolsmith.py",
            "scripts/openclaw/agent_society_kernel.py",
        ]:
            path = sandbox_repo.joinpath(*rel.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# placeholder\n", encoding="utf-8")

        created = create_helper_tool(
            repo_root=sandbox_repo,
            helper_name="timeout repairer",
            purpose="repair repeated timeout failures without drifting away from the original goal",
            category="runtime_timeout",
        )
        helper_path = sandbox_repo.joinpath(*str(created["entrypoint"]).split("/"))
        run = subprocess.run(
            [
                sys.executable,
                str(helper_path),
                "--repo-root",
                str(sandbox_repo),
                "--observation",
                "cron job execution timed out while waiting for first response",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(run.stdout)
        if payload["status"] != "ready":
            raise AssertionError(f"expected ready business repairer, got {payload['status']}")
        if len(payload.get("repair_workflow", [])) < 3:
            raise AssertionError(f"expected multi-step repair workflow, got {payload.get('repair_workflow')}")
        if not payload.get("drift", {}).get("ok"):
            raise AssertionError(f"expected drift guard to pass, got {payload.get('drift')}")
        if payload.get("contract", {}).get("purpose_hash") != created.get("purpose_hash"):
            raise AssertionError("expected helper contract purpose hash to round-trip")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
