#!/usr/bin/env python3
"""
Deprecated historical OpenClaw router migration.

The v7 migration kept local Qwen/Ollama in the primary intent-classifier path.
Current policy is Codex primary with Qwen/Ollama fallback only, delivered through
Git-managed configuration and the current v8 patch.
"""
import sys


def main() -> int:
    print(
        "DEPRECATED: patch_news_router_current_to_v7.py is disabled because "
        "it preserves legacy Qwen/Ollama-first routing. Use the current "
        "Codex-primary v8 path instead."
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
