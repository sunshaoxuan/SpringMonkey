#!/usr/bin/env python3
from __future__ import annotations

import sys


def main() -> int:
    print(
        "DEPRECATED: this legacy deployment path encoded Ollama-first behavior. "
        "Use Git-delivered Codex-first config and repo-sync instead.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
