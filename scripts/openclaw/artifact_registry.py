#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_STATE_PATH = Path("/var/lib/openclaw/.openclaw/workspace/state/artifacts/latest_google_doc.json")
DOC_URL_RE = re.compile(r"https://docs\.google\.com/document/d/[^\s)>\"]+")


def normalize_doc_url(value: str) -> str:
    match = DOC_URL_RE.search(value or "")
    return match.group(0).rstrip(".,，。") if match else ""


def load_latest_artifact(path: Path = DEFAULT_STATE_PATH) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict) or not normalize_doc_url(str(payload.get("url") or "")):
        return None
    return payload


def record_artifact(url: str, source: str, *, path: Path = DEFAULT_STATE_PATH) -> dict[str, Any]:
    normalized = normalize_doc_url(url)
    if not normalized:
        raise ValueError("a valid Google Docs document URL is required")
    payload = {
        "kind": "google_doc",
        "url": normalized,
        "source": source.strip() or "unknown",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintain the authoritative latest delivered artifact record.")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record")
    record.add_argument("--url", required=True)
    record.add_argument("--source", required=True)
    sub.add_parser("latest")
    args = parser.parse_args()
    if args.command == "record":
        payload = record_artifact(args.url, args.source, path=args.state)
    else:
        payload = load_latest_artifact(args.state)
        if payload is None:
            print(json.dumps({"status": "missing"}, ensure_ascii=False))
            return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
