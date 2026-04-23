#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def write_required_toolsmith_paths(repo_root: Path) -> None:
    for rel in [
        "scripts/openclaw/agent_society_runtime_record_gap.py",
        "scripts/openclaw/agent_society_helper_toolsmith.py",
        "scripts/openclaw/agent_society_kernel.py",
    ]:
        path = repo_root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# test placeholder\n", encoding="utf-8")


def main() -> int:
    source_repo = Path(__file__).resolve().parents[2]
    script = source_repo / "scripts" / "openclaw" / "job_orchestrator.py"
    with tempfile.TemporaryDirectory(prefix="job_orchestrator_failure_") as tmp:
        root = Path(tmp)
        fake_repo = root / "repo"
        write_required_toolsmith_paths(fake_repo)
        # Use the real runtime gap script and its imports, but let helper generation target the fake repo.
        real_openclaw = source_repo / "scripts" / "openclaw"
        for name in [
            "agent_society_runtime_record_gap.py",
            "agent_society_helper_toolsmith.py",
            "agent_society_kernel.py",
        ]:
            fake_path = fake_repo / "scripts" / "openclaw" / name
            fake_path.write_text((real_openclaw / name).read_text(encoding="utf-8"), encoding="utf-8")

        state = root / "attempts.json"
        command = root / "flaky.py"
        command.write_text(
            "\n".join(
                [
                    "import json, pathlib, sys",
                    f"state = pathlib.Path({str(state)!r})",
                    "count = json.loads(state.read_text())['count'] if state.exists() else 0",
                    "state.write_text(json.dumps({'count': count + 1}))",
                    "if count == 0:",
                    "    print('timeout while waiting for first response', file=sys.stderr)",
                    "    raise SystemExit(2)",
                    "print('recovered report')",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--job-name",
                "line-watchdog-test",
                "--category",
                "generic",
                "--prompt",
                "handle timeout and retry",
                "--kernel-root",
                str(root / "kernel"),
                "--repo-root",
                str(fake_repo),
                "--max-retries",
                "1",
                "--command",
                sys.executable,
                str(command),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        if proc.stdout.strip() != "recovered report":
            raise AssertionError(f"expected recovered stdout, got {proc.stdout!r} stderr={proc.stderr!r}")
        sessions = list((root / "kernel" / "sessions").glob("session_*.json"))
        if len(sessions) < 1:
            raise AssertionError("expected kernel session")
        loaded = [json.loads(path.read_text(encoding="utf-8")) for path in sessions]
        data = next((item for item in loaded if item.get("capability_gaps")), loaded[0])
        if not data.get("capability_gaps"):
            raise AssertionError("expected capability gap from failed first attempt")
        if not data.get("helper_tools"):
            raise AssertionError("expected helper tool from failed first attempt")
        if data["observations"][-1].get("status") != "completed":
            raise AssertionError("expected final completed observation after retry")
        print("job_orchestrator_failure_self_repair_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
