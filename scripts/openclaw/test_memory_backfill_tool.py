from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import memory_backfill_tool as tool


def test_memory_backfill_dry_run_extracts_xhs_candidates() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        sessions = Path(tmp) / "sessions"
        sessions.mkdir()
        (sessions / "session_xhs.jsonl").write_text(
            json.dumps({"content": "小红书投稿：日本 Costco 热门甜品，包含 Frutteto 和草莓巧克力话题。"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        candidates = tool.collect_candidates("xhs", sessions, None)
    assert len(candidates) == 1
    assert "XHS 长记忆回填" in candidates[0].text
    assert "Costco" in candidates[0].text


def test_memory_backfill_write_uses_embedding_and_lancedb_insert() -> None:
    candidate = tool.MemoryCandidate(topic="xhs", source="session.jsonl", text="XHS 长记忆回填：小红书投稿流程。")
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "backfill.jsonl"
        with patch.object(tool, "embed_text", return_value=[0.0] * tool.DEFAULT_DIMENSIONS) as embed, patch.object(tool, "node_insert_lancedb") as insert:
            rows = tool.write_candidates(
                [candidate],
                db_path=Path(tmp) / "lancedb",
                base_url="http://127.0.0.1:11434",
                model=tool.DEFAULT_EMBED_MODEL,
                dimensions=tool.DEFAULT_DIMENSIONS,
                backfill_log=log,
            )
        assert len(rows) == 1
        embed.assert_called_once()
        insert.assert_called_once()
        assert "小红书投稿流程" in log.read_text(encoding="utf-8")
