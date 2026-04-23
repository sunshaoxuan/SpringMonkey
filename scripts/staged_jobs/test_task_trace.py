#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import task_trace as mod


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="staged_task_trace_") as tmp:
        mod.TRACE_ROOT = Path(tmp)
        trace = mod.StagedTaskTrace("weather-report-jst-0700", "weather")
        trace.start("fetch")
        trace.step("fetch", "ok", detail="done", tool="http")
        trace.artifact("run_dir", "/tmp/example")
        trace.finish("ok", "done", final_message="hello")
        payload = json.loads((Path(tmp) / "weather" / "weather-report-jst-0700.latest.json").read_text(encoding="utf-8"))
        assert payload["status"] == "ok"
        assert payload["currentPhase"] == "done"
        assert payload["artifacts"]["run_dir"] == "/tmp/example"
        print(json.dumps({"steps": len(payload["steps"]), "status": payload["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
