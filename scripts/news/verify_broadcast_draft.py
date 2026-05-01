#!/usr/bin/env python3
"""
对新闻播报成稿做机械格式校验（不调用模型）。
从 broadcast.json 读取 outline / titleLine / formatRules。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "news" / "broadcast.json"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def verify_text(text: str, cfg: dict) -> tuple[bool, list[str]]:
    errors: list[str] = []
    fr = cfg.get("formatRules", {})
    title = fr.get("titleLine", "新闻简报")
    outline: list[str] = fr.get("outline", [])
    forbid_nested = fr.get("forbidNestedNumbering", True)
    self_check = fr.get("selfCheckNumberedLinesOnlyTopLevel", True)

    lines = text.splitlines()
    flat = "\n".join(lines)
    outline_set = set(outline)

    if re.search(r"<think>.*?</think>", flat, flags=re.IGNORECASE | re.DOTALL):
        errors.append("contains_think_block: 成稿中出现 <think> 思维链内容")

    if title not in flat:
        errors.append(f"missing_title: 正文中应出现标题「{title}」")

    # outline 匹配：按顺序检查每个 outline 条目是否作为独立行出现
    found_outline: list[str] = []
    for ln in lines:
        s = ln.strip()
        if s in outline_set:
            found_outline.append(s)
    if found_outline != outline:
        errors.append(
            f"bad_top_level_numbering: 期望 {outline!r}, 实际 {found_outline!r}"
        )

    bullet_prefix = fr.get("contentBulletPrefix", "• ")
    if not fr.get("includeLinksInBroadcast", True):
        url_pattern = re.compile(r"(https?://|www\.|[A-Za-z0-9-]+\.(?:com|net|org|jp|cn|co|io|ai)(?:/|\b))")
        for i, ln in enumerate(lines, 1):
            if url_pattern.search(ln):
                errors.append(f"link_in_broadcast_line_{i}: {ln[:120]!r}")
            if ln.strip().startswith("链接："):
                errors.append(f"link_label_in_broadcast_line_{i}: {ln[:120]!r}")

    if forbid_nested:
        for i, ln in enumerate(lines, 1):
            s = ln.strip()
            if s in outline_set:
                continue
            # 独立行以裸数字编号开头（如 1. xxx / 2) xxx），且不是 outline
            if re.match(r"^\*{0,2}\d+[\.\)）]\s", s):
                errors.append(f"bare_numbered_line_{i}: {ln[:80]!r}")
            # 缩进行以数字编号开头
            if re.match(r"^\s+\d+[\.\)）]\s", ln):
                errors.append(f"nested_numbering_line_{i}: {ln[:80]!r}")
            # 条目符号后接数字编号：「• 1. xxx」「- 1. xxx」「• **1.** xxx」
            if re.match(r"^\s*[•\-]\s+\*{0,2}\d+[\.\)）]\s*\*{0,2}\s+", ln):
                errors.append(f"numbered_inside_bullet_line_{i}: {ln[:80]!r}")
            # 「• 1、xxx」「- 1、xxx」
            if re.match(r"^\s*[•\-]\s+\d+[、，]\s*", ln):
                errors.append(f"numbered_inside_bullet_cn_line_{i}: {ln[:80]!r}")

    def mostly_chinese_item(s: str) -> bool:
        body = s.strip()
        if not body.startswith(bullet_prefix):
            return True
        body = body[len(bullet_prefix):].strip()
        if "外文新闻" in body:
            return False
        if re.search(r"[\u3040-\u30ff]", body):
            return False
        if body == fr.get("fallbackNoMajorUpdateLine", "本节无合格新增新闻条目。"):
            return True
        letters = [ch for ch in body if ch.isalpha() or "\u4e00" <= ch <= "\u9fff"]
        if len(letters) < 12:
            return True
        cjk = sum(1 for ch in letters if "\u4e00" <= ch <= "\u9fff")
        return cjk / len(letters) >= 0.35

    for i, ln in enumerate(lines, 1):
        if ln.strip().startswith(bullet_prefix) and not mostly_chinese_item(ln):
            errors.append(f"non_chinese_news_item_line_{i}: {ln[:120]!r}")

    ok = len(errors) == 0
    return ok, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="机械校验新闻播报成稿格式。")
    parser.add_argument(
        "path",
        nargs="?",
        help="成稿文件路径；缺省从 stdin 读",
    )
    parser.add_argument(
        "--config",
        default=str(CONFIG_PATH),
        help="broadcast.json 路径",
    )
    args = parser.parse_args()
    cfg = load_json(Path(args.config))
    if args.path:
        text = Path(args.path).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    ok, errors = verify_text(text, cfg)
    if ok:
        print("VERIFY_DRAFT_OK")
        return 0
    print("VERIFY_DRAFT_FAIL", file=sys.stderr)
    for e in errors:
        print(e, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
