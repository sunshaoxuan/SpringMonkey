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

    if title not in flat:
        errors.append(f"missing_title: 正文中应出现标题「{title}」")

    top_numbered = [ln for ln in lines if re.match(r"^\d+\.\s", ln)]
    if top_numbered != outline:
        errors.append(
            f"bad_top_level_numbering: 期望 {outline!r}, 实际 {top_numbered!r}"
        )

    outline_set = set(outline)
    if self_check:
        for i, ln in enumerate(lines, 1):
            if re.match(r"^\d+\.\s", ln) and ln not in outline_set:
                errors.append(f"unexpected_numbered_line_{i}: {ln[:80]!r}")

    if forbid_nested:
        for i, ln in enumerate(lines, 1):
            if re.match(r"^\s+\d+\.\s+", ln):
                errors.append(f"nested_numbering_line_{i}: {ln[:80]!r}")
            # 「- 1. xxx」「- **1.** xxx」「- （1）xxx」等
            if re.match(r"^\s*-\s+\*{0,2}\d+[\.\)）]\s*\*{0,2}\s+", ln):
                errors.append(f"numbered_inside_bullet_line_{i}: {ln[:80]!r}")
            # 「- 1、xxx」
            if re.match(r"^\s*-\s+\d+[、，]\s*", ln):
                errors.append(f"numbered_inside_bullet_cn_line_{i}: {ln[:80]!r}")

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
