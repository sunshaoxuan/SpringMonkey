#!/usr/bin/env python3
"""Retired OpenClaw runtime patch.

The old v8 patch rewrote the embedded Discord router to fall back from Codex to
Ollama/Qwen on port 22545. That endpoint is retired. Keeping this entrypoint as
a hard failure prevents accidental production drift from stale runbooks.
"""
from __future__ import annotations


def main() -> int:
    print("PATCH_V8_RETIRED: 22545 Ollama/Qwen fallback is no longer supported.")
    print("Use scripts/remote_install_model_auth_profile_guard.py for the 49530-only model baseline.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
