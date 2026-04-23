#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import run_news_pipeline as mod


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="news_trace_") as tmp:
        run_dir = Path(tmp) / "run"
        import staged_jobs.task_trace as trace_mod

        trace_mod.TRACE_ROOT = Path(tmp) / "traces"
        args = [
            "--config",
            str(mod.DEFAULT_CONFIG),
            "--job",
            "news-digest-jst-0900",
            "--run-dir",
            str(run_dir),
            "--dry-run",
            "--skip-verify",
            "--skip-finalize",
        ]
        import sys

        saved = sys.argv[:]
        try:
            sys.argv = ["run_news_pipeline.py", *args]
            rc = mod.main()
        finally:
            sys.argv = saved
        if rc != 0:
            raise AssertionError(f"expected rc=0, got {rc}")
        trace_path = Path(tmp) / "traces" / "news" / "news-digest-jst-0900.latest.json"
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
        assert payload["status"] == "ok"
        assert payload["currentPhase"] == "skip-finalize"
        assert payload["artifacts"]["run_dir"] == str(run_dir.resolve())
        print(json.dumps({"steps": len(payload["steps"]), "status": payload["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
