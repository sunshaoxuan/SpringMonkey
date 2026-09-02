#!/usr/bin/env python3
"""Retired compatibility wrapper for the old Ollama fallback installer.

The 22545 Ollama/Qwen fallback is no longer part of the OpenClaw runtime
baseline. Running this legacy entrypoint now applies the 49530-only model auth
guard so old operational notes cannot restore the retired fallback.
"""
from __future__ import annotations

from remote_install_model_auth_profile_guard import main


if __name__ == "__main__":
    raise SystemExit(main())
