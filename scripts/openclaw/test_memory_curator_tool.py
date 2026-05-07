from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import memory_curator_tool as curator


def test_curator_marks_xhs_noise_and_ignores_clean_memory() -> None:
    entries = [
        curator.MemoryEntry(
            id="11111111-1111-1111-1111-111111111111",
            text='XHS 长记忆回填：{"encrypted_content":"gAAAAA"} /tmp/a.png /tmp/b.png',
            category="fact",
            importance=0.7,
            createdAt=1,
        ),
        curator.MemoryEntry(
            id="22222222-2222-2222-2222-222222222222",
            text="XHS 长记忆回填：Costco 日本官网产品图 1 无水印，Frutteto 官方图片 2 可用于小红书投稿。",
            category="fact",
            importance=0.7,
            createdAt=2,
        ),
    ]
    marked = curator.curate(entries, "xhs")
    assert len(marked) == 1
    assert marked[0].id.startswith("1111")
    assert "encrypted" in marked[0].reason


def test_curator_preserves_high_value_xhs_even_with_path_noise() -> None:
    entries = [
        curator.MemoryEntry(
            id="33333333-3333-3333-3333-333333333333",
            text="XHS 长记忆回填：Costco 日本官网产品图 1 无水印；Frutteto 官方图片 2 无水印；/tmp/a.png /tmp/b.png /tmp/c.png /tmp/d.png /tmp/e.png /tmp/f.png /tmp/g.png /tmp/h.png /tmp/i.png /tmp/j.png /tmp/k.png",
            category="fact",
            importance=0.7,
            createdAt=3,
        )
    ]
    assert curator.curate(entries, "xhs") == []


def test_delete_marked_deletes_only_supplied_ids() -> None:
    with patch.object(curator, "node_lancedb", return_value={"deleted": ["11111111-1111-1111-1111-111111111111"]}) as node:
        deleted = curator.delete_marked(curator.DEFAULT_DB_PATH, ["11111111-1111-1111-1111-111111111111"])
    assert deleted == ["11111111-1111-1111-1111-111111111111"]
    assert node.call_args.args[0]["action"] == "delete"
    assert node.call_args.args[0]["ids"] == ["11111111-1111-1111-1111-111111111111"]


def test_curator_writes_audit_for_deleted_rows() -> None:
    marked = [
        curator.CuratedMemory(
            id="11111111-1111-1111-1111-111111111111",
            reason="contains encrypted/base64/path-log noise",
            text_preview="XHS noise",
            score=3,
        )
    ]
    with tempfile.TemporaryDirectory() as tmp:
        audit = Path(tmp) / "audit.jsonl"
        curator.write_audit("xhs", marked, ["11111111-1111-1111-1111-111111111111"], audit)
        rows = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]

    assert rows[0]["topic"] == "xhs"
    assert rows[0]["deleted_count"] == 1
