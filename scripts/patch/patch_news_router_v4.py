#!/usr/bin/env python3
"""
Deprecated historical OpenClaw router patch.

This v4 patch encoded Ollama-first failure counting and fallback to Codex.
Current policy is the inverse: Codex is primary, Qwen/Ollama is fallback only.
"""
import sys


def main() -> int:
    print(
        "DEPRECATED: patch_news_router_v4.py is disabled because it encodes "
        "legacy Ollama-first behavior. Use the current Codex-primary v8 path."
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
