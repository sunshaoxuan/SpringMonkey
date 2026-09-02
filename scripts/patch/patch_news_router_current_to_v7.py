#!/usr/bin/env python3
"""
Deprecated historical OpenClaw router migration.

The v7 migration kept local Qwen/Ollama in the primary intent-classifier path.
Current policy is Spark through sub2api with no active chat fallback unless a
smoke-gated fallback installer enables one.
"""
import sys


def main() -> int:
    print(
        "DEPRECATED: patch_news_router_current_to_v7.py is disabled because "
        "it preserves legacy Qwen/Ollama-first routing. Use the current "
        "Spark/sub2api v8 path instead."
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
