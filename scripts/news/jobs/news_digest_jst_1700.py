#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "news" / "run_news_pipeline.py"


def main() -> int:
    cmd = [sys.executable, str(SCRIPT), "--job", "news-digest-jst-1700"]
    return subprocess.call(cmd, cwd=str(REPO_ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
