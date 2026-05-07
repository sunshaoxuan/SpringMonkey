from __future__ import annotations

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


def test_delete_marked_deletes_only_supplied_ids() -> None:
    with patch.object(curator, "node_lancedb", return_value={"deleted": ["11111111-1111-1111-1111-111111111111"]}) as node:
        deleted = curator.delete_marked(curator.DEFAULT_DB_PATH, ["11111111-1111-1111-1111-111111111111"])
    assert deleted == ["11111111-1111-1111-1111-111111111111"]
    assert node.call_args.args[0]["action"] == "delete"
    assert node.call_args.args[0]["ids"] == ["11111111-1111-1111-1111-111111111111"]
