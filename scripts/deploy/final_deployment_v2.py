#!/usr/bin/env python3
from __future__ import annotations

import sys


def main() -> int:
    print(
        "DEPRECATED: legacy Ollama-first deployment script disabled. "
        "Current production uses openai-codex/gpt-5.3-codex-spark through sub2api.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
