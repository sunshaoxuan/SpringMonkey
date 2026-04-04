#!/usr/bin/env python3
"""
单元测试：与 pi-embedded 中手动重跑新闻启发式保持一致（不依赖 Ollama / OpenClaw）。
运行：python3 scripts/openclaw/test_manual_news_heuristics.py
"""
from __future__ import annotations

import re
import sys
import unittest


def has_explicit_news_slot_hint(text: str) -> bool:
    return bool(
        re.search(r"(17\s*[:：点时]|17点|17時|十七点|1700)", text)
        or re.search(r"(0?9\s*[:：点时]|9点|09点|09時|9時|0900)", text)
        or re.search(r"news-digest-jst-(0900|1700)", text, re.I)
    )


def is_manual_news_rerun_prompt(text: str) -> bool:
    return bool(
        re.search(
            r"(重跑|重新跑|重新执行|手动重跑|立即手动重跑|立即重跑|再次执行|再跑一次|再跑一遍|"
            r"跑一次|跑一遍|来一次|立即执行|马上执行|现在就跑|触发|rerun|run again|restart)",
            text,
            re.I,
        )
    )


def should_override_to_news_task(text: str) -> bool:
    if not is_manual_news_rerun_prompt(text) or not has_explicit_news_slot_hint(text):
        return False
    return bool(
        re.search(
            r"(新闻|播报|digest|news|摘要|cron|正式任务|正式规则)",
            text,
            re.I,
        )
    )


class TestHeuristics(unittest.TestCase):
    def test_user_regression_message(self):
        s = (
            "汤猴，请按当前正式规则，立即手动重跑一次 17:00 新闻播报，"
            "并只回复最终结果，不要连续发送中间过程。"
        )
        self.assertTrue(should_override_to_news_task(s))

    def test_negative_chat(self):
        self.assertFalse(should_override_to_news_task("今天天气怎么样"))

    def test_slot_without_rerun(self):
        self.assertFalse(
            should_override_to_news_task("17:00 新闻里有什么")
        )


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestHeuristics)
    r = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
