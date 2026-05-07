from __future__ import annotations

import intent_tool_router as router


def test_memory_curator_check_is_dry_run() -> None:
    tool = {"args_schema": {"mode": "memory_curator", "topic": "xhs", "forget_marked": False, "limit": 25}}
    args = router.extract_args(tool, "检查长记忆质量", "2026-05-08T00:00:00+09:00")
    assert args["forget_marked"] is False


def test_memory_curator_clean_without_confirmation_is_dry_run() -> None:
    tool = {"args_schema": {"mode": "memory_curator", "topic": "xhs", "forget_marked": False, "limit": 25}}
    args = router.extract_args(tool, "清理小红书长记忆噪声", "2026-05-08T00:00:00+09:00")
    assert args["forget_marked"] is False


def test_memory_curator_confirm_clean_enables_forget_marked() -> None:
    tool = {"args_schema": {"mode": "memory_curator", "topic": "xhs", "forget_marked": False, "limit": 25}}
    args = router.extract_args(tool, "确认清理小红书长记忆噪声", "2026-05-08T00:00:00+09:00")
    assert args["forget_marked"] is True
