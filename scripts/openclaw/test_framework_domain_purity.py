#!/usr/bin/env python3
from __future__ import annotations

import re
import ast
from pathlib import Path


FRAMEWORK_FILES = [
    Path("scripts/openclaw/agent_society_kernel.py"),
    Path("scripts/openclaw/job_orchestrator.py"),
]

FORBIDDEN_DOMAIN_TERMS = [
    "timescar",
    "weather",
    "news",
    "line",
    "discord",
]

ALLOWED_SUBSTRINGS = [
    "delivery-channel",
    "delivery_channel",
    "delivery-to",
    "delivery_to",
]


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    violations: list[str] = []
    for relative in FRAMEWORK_FILES:
        path = repo_root / relative
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        text = "\n".join(
            value.lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            if isinstance((value := node.value), str)
        )
        for allowed in ALLOWED_SUBSTRINGS:
            text = text.replace(allowed, "")
        for term in FORBIDDEN_DOMAIN_TERMS:
            pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
            if re.search(pattern, text):
                violations.append(f"{relative}: contains domain term {term!r}")
    if violations:
        raise AssertionError("\n".join(violations))
    print("framework_domain_purity_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
