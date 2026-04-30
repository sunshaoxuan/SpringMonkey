#!/usr/bin/env python3
from __future__ import annotations

import sys


def main() -> int:
    print(
        "DEPRECATED: ad-hoc SSH deployment is disabled. "
        "OpenClaw behavior changes must be committed and pushed through Git; "
        "the host must obtain them through repo-sync / controlled pull.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
