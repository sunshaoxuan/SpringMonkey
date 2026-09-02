#!/usr/bin/env python3
"""
Deprecated historical OpenClaw intent-router patch.

This v6 patch encoded Qwen/Ollama-first classifier behavior. Current OpenClaw
policy is Spark through sub2api with no active chat fallback unless a
smoke-gated fallback installer enables one. Use scripts/openclaw/patch_news_router_v8.py
for the current Git-delivered route.
"""
import sys


def main() -> int:
    print(
        "DEPRECATED: patch_news_router_v6.py is disabled because it encodes "
        "legacy Qwen/Ollama-first behavior. Use patch_news_router_v8.py for "
        "Spark/sub2api routing."
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
