#!/usr/bin/env python3
"""
Validate docs/registry/tools_and_skills_manifest.json:
  - JSON syntax
  - required fields and id/type/path rules
  - each path exists under repository root (relative)

Run from repo root: python scripts/registry/verify_tools_manifest.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_ID_RE = re.compile(r"^[a-z0-9._-]+$")
_ALLOWED_TYPES = frozenset(
    {"policy_doc", "doc", "script", "skill", "config", "test", "patch"}
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    root = repo_root()
    manifest_path = root / "docs" / "registry" / "tools_and_skills_manifest.json"
    if not manifest_path.is_file():
        print(f"MISSING: {manifest_path}", file=sys.stderr)
        return 2
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"INVALID JSON: {e}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("ROOT must be object", file=sys.stderr)
        return 2
    if data.get("schema_version") != 1:
        print("schema_version must be 1", file=sys.stderr)
        return 2
    items = data.get("items")
    if not isinstance(items, list) or not items:
        print("items must be non-empty array", file=sys.stderr)
        return 2
    seen: set[str] = set()
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            print(f"items[{i}] must be object", file=sys.stderr)
            return 2
        for k in ("id", "type", "path"):
            if k not in it:
                print(f"items[{i}] missing {k}", file=sys.stderr)
                return 2
        extra = set(it.keys()) - {"id", "type", "path", "summary"}
        if extra:
            print(f"items[{i}] unknown keys: {extra}", file=sys.stderr)
            return 2
        iid, typ, relp = it["id"], it["type"], it["path"]
        if not isinstance(iid, str) or not _ID_RE.match(iid):
            print(f"items[{i}] bad id: {iid!r}", file=sys.stderr)
            return 2
        if iid in seen:
            print(f"duplicate id: {iid}", file=sys.stderr)
            return 2
        seen.add(iid)
        if typ not in _ALLOWED_TYPES:
            print(f"items[{i}] bad type: {typ!r}", file=sys.stderr)
            return 2
        if not isinstance(relp, str) or not relp or relp.startswith(("/", "\\")):
            print(f"items[{i}] path must be relative non-empty: {relp!r}", file=sys.stderr)
            return 2
        full = (root / relp).resolve()
        try:
            full.relative_to(root.resolve())
        except ValueError:
            print(f"items[{i}] path escapes repo: {relp}", file=sys.stderr)
            return 2
        if not full.is_file():
            print(f"MISSING FILE: {relp}", file=sys.stderr)
            return 2
        if "summary" in it and not isinstance(it["summary"], str):
            print(f"items[{i}] summary must be string if present", file=sys.stderr)
            return 2
    print("MANIFEST_OK", len(items), "items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())