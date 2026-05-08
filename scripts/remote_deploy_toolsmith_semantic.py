#!/usr/bin/env python3
"""Deploy semantic toolsmith changes through Git truth and run remote smoke checks."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, check: bool = True) -> int:
    print("$ " + " ".join(command))
    proc = subprocess.run(command, cwd=ROOT, text=True, encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise SystemExit(proc.returncode)
    return proc.returncode


def main() -> int:
    checks = [
        [sys.executable, "-m", "pytest", "-q", "scripts/openclaw/test_toolsmith_repair_runner.py", "scripts/openclaw/test_capability_repair_runner.py"],
        [sys.executable, "scripts/openclaw/verify_intent_tool_registry.py"],
        [sys.executable, "scripts/openclaw/verify_harness_registry.py"],
    ]
    for command in checks:
        run(command)

    run(["git", "status", "--short"])
    run(["git", "push", "origin", "main"])
    run([sys.executable, "scripts/openclaw_remote_cli.py", "git-pull"])
    run([sys.executable, "scripts/openclaw_remote_cli.py", "toolsmith-verify"])
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
