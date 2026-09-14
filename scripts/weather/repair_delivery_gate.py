"""Align the installed weather delivery gate with the current producer contract."""
from __future__ import annotations

import argparse
import ast
import os
import stat
import tempfile
from pathlib import Path


def repaired_source(source: str) -> str:
    nodes = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "should_deliver_public"]
    if len(nodes) != 1:
        raise ValueError("Expected one public delivery gate")
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    section = "".join(lines[node.lineno - 1:node.end_lineno])
    old = 'path.name.endswith("_image2.png")'
    new = 'path.name.endswith("_model.png")'
    if new in section and old not in section:
        return source
    if section.count(old) != 1 or new in section:
        raise ValueError("Unrecognized weather gate; inspect before changing it")
    lines[node.lineno - 1:node.end_lineno] = [section.replace(old, new)]
    result = "".join(lines)
    compile(result, "delivery_helper", "exec")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=Path("/usr/local/lib/openclaw/direct_cron_to_discord.py"))
    args = parser.parse_args()
    source = args.path.read_text(encoding="utf-8")
    updated = repaired_source(source)
    if source == updated:
        print("GATE=current")
        return 0
    original = args.path.stat()
    fd, temporary = tempfile.mkstemp(prefix=".weather-gate-", dir=args.path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(original.st_mode))
        if hasattr(os, "chown"):
            os.chown(temporary, original.st_uid, original.st_gid)
        os.replace(temporary, args.path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    assert args.path.read_text(encoding="utf-8") == updated
    print("GATE=repaired")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
