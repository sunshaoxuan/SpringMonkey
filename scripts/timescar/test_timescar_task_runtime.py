#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="timescar_runtime_") as tmp:
        import task_runtime as runtime_module

        workspace = Path(tmp)
        runtime_module.WORKSPACE = workspace
        runtime_module.TRACE_DIR = workspace / "state" / "timescar_traces"
        runtime_module.GUARD_SCRIPT = workspace / "scripts" / "timescar_task_guard.py"

        runtime = runtime_module.TimesCarTaskRuntime("timescar-book-sat-3weeks", "write", ttl_seconds=120)
        runtime.start("init")
        runtime.record_step(step="open-page", status="ok", tool="browser", detail="opened page")
        runtime.heartbeat("login", note="session requires login")
        runtime.finish("ok", "done", final_message="booked")

        payload = json.loads((workspace / "state" / "timescar_traces" / "timescar-book-sat-3weeks.latest.json").read_text(encoding="utf-8"))
        assert payload["status"] == "ok"
        assert payload["currentPhase"] == "done"
        assert payload["finalMessage"] == "booked"
        assert payload["steps"][0]["step"] == "open-page"
        print(json.dumps({"trace_steps": len(payload["steps"]), "status": payload["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
