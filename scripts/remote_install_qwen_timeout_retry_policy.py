#!/usr/bin/env python3
from __future__ import annotations

import sys


def main() -> int:
    print(
        "DEPRECATED: qwen-first timeout retry policy is disabled. "
        "Current OpenClaw default is openai-codex/gpt-5.5 primary with "
        "ollama/qwen3:14b fallback only. Update behavior through Git-delivered "
        "config and scripts, then let the host pull the repository.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
