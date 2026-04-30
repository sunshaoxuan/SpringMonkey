#!/usr/bin/env python3
from __future__ import annotations

import sys


def main() -> int:
    print(
        "DEPRECATED: legacy patch deploy encoded Ollama-first failover. "
        "Current policy is Codex primary with Qwen/Ollama fallback, delivered through Git.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
