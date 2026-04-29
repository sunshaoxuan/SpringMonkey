#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from openclaw_remote_cli import TOOLS


ROOT = Path(__file__).resolve().parents[1]


def test_reply_media_repair_is_registered() -> None:
    assert TOOLS["reply-media-repair"] == "remote_repair_reply_media_images.py"
    assert (ROOT / "scripts" / TOOLS["reply-media-repair"]).is_file()


def test_reply_media_repair_is_documented() -> None:
    docs = [
        ROOT / "docs" / "ops" / "TOOLS_REGISTRY.md",
        ROOT / "scripts" / "INDEX.md",
        ROOT / "docs" / "CAPABILITY_INDEX.md",
    ]
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        assert "remote_repair_reply_media_images.py" in text


def main() -> int:
    test_reply_media_repair_is_registered()
    test_reply_media_repair_is_documented()
    print("openclaw_remote_cli_registry_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
