#!/usr/bin/env python3
"""
Deprecated historical OpenClaw intent-router patch.

This v6 patch encoded Qwen/Ollama-first classifier behavior. Current OpenClaw
policy is Codex primary with Qwen/Ollama fallback only. Use
scripts/openclaw/patch_news_router_v8.py for the current Git-delivered route.
"""
import sys


def main() -> int:
    print(
        "DEPRECATED: patch_news_router_v6.py is disabled because it encodes "
        "legacy Qwen/Ollama-first behavior. Use patch_news_router_v8.py for "
        "Codex-primary, Qwen-fallback routing."
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
