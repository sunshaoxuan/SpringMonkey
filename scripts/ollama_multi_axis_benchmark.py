#!/usr/bin/env python3
"""
多维度 Ollama 对比：逻辑、翻译、代码、表达、理解、新闻结构、指令遵循、数理、歧义等。

面向「新闻 worker / 主语义」选型：与 broadcast.json 中 newsWorker 候选同场对比。

用法：
  set OLLAMA_BASE=http://ccnode.briconbric.com:22545
  python scripts/ollama_multi_axis_benchmark.py --output-md report.md --output-json report.json

多轮（同一套题重复，看稳定性）：
  python scripts/ollama_multi_axis_benchmark.py --rounds 2 --output-md report.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_BASE = os.environ.get("OLLAMA_BASE", "http://127.0.0.1:11434")

DEFAULT_MODELS = ["qwen3:14b", "gemma3:12b"]


@dataclass
class AxisItem:
    id: str
    axis_zh: str
    prompt: str


# 各维度一题：短上下文、可人工判分；与新闻流水线「摘要/分类/遵从格式」相关
AXIS_PROMPTS: list[AxisItem] = [
    AxisItem(
        "logic",
        "逻辑（演绎）",
        "有三个断言：A) 所有在本店买咖啡的顾客都拿到积分。B) 小明拿到积分。C) 小明一定在本店买过咖啡。"
        "问：C 是否必然由 A 和 B 推出？只回答第一行「是」或「否」，第二行理由不超过25字。",
    ),
    AxisItem(
        "numeracy",
        "数理（陷阱）",
        "某商品先涨价10%再降价10%，最终相对原价变化多少？只答一个百分数（如-1%），不要过程。",
    ),
    AxisItem(
        "translation",
        "翻译（英→中）",
        "将下面英文新闻句译为简体中文（只输出译文，不要解释）："
        "The Fed held rates steady while signaling two cuts later this year.",
    ),
    AxisItem(
        "translation_names",
        "翻译（专名）",
        "以下英文人名在中文新闻里的常见译名？只写译名，一行一个，共两行：\n1. Sanae Takaichi\n2. Jerome Powell",
    ),
    AxisItem(
        "code",
        "代码（可执行）",
        "只输出一个 Python 代码块（markdown 代码块也可以），实现："
        "def clip_middle(s: str, max_len: int) -> str：若 len(s)<=max_len 返回 s；否则返回 s 前 floor(max_len/2) 字符 + '…' + s 后 ceil(max_len/2) 字符。"
        "不要长篇解释。",
    ),
    AxisItem(
        "expression",
        "表达（标题压缩）",
        "把下面口语改写成不超过28字的中文简讯标题（不要句末句号）："
        "就是说那个公司说他们可能要裁员但是还没定具体人数",
    ),
    AxisItem(
        "understanding",
        "理解（信息边界）",
        "段落：某市地铁宣布周末抢修，3号线周日全天停运，其他线路缩短班次。问：周一 3号线是否一定恢复运营？"
        "第一行只答「能确定」「不能确定」「段落未说明」之一；第二行理由不超过20字。",
    ),
    AxisItem(
        "news_struct",
        "新闻结构化（JSON）",
        "根据碎片仅输出一行合法 JSON（不要 markdown），键：title(str), region(str), sentiment(仅 positive|negative|neutral 之一)。"
        "碎片：日本央行维持政策利率不变，日元对美元短线走弱。",
    ),
    AxisItem(
        "instruction",
        "指令遵循（格式）",
        "严格输出三行：第一行只写数字 1，第二行只写数字 2，第三行只写大写字母 OK。不要空行，不要其他任何字符。",
    ),
    AxisItem(
        "ambiguity",
        "歧义辨析",
        "句子「负责人走了」在中文里可能指哪两种不同含义？每行一个短句说明，共两行，行首不要编号。",
    ),
]


def _ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def get_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def post_json(url: str, body: dict, timeout: int = 600) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def chat(base: str, model: str, user_prompt: str, timeout: int = 600) -> tuple[str, int]:
    url = base.rstrip("/") + "/api/chat"
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": user_prompt}],
        "stream": False,
    }
    if model.lower().startswith("qwen3"):
        body["think"] = False
    t0 = time.perf_counter()
    out = post_json(url, body, timeout=timeout)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    msg = out.get("message") or {}
    text = msg.get("content") or json.dumps(out, ensure_ascii=False)[:4000]
    return text.strip(), elapsed_ms


def parse_models_arg(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="多维度 Ollama 新闻语义选型对比")
    ap.add_argument("--base", default=os.environ.get("OLLAMA_BASE", DEFAULT_BASE))
    ap.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help="逗号分隔，如 qwen3:14b,gemma3:12b",
    )
    ap.add_argument("--rounds", type=int, default=1, help="同一套题重复轮数（稳定性）")
    ap.add_argument("--timeout", type=int, default=600, help="单次 chat 超时秒")
    ap.add_argument("--output-md", metavar="FILE", help="写入 Markdown 报告（UTF-8）")
    ap.add_argument("--output-json", metavar="FILE", help="写入 JSON 原始结果（UTF-8）")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    models = parse_models_arg(args.models)
    _ensure_utf8_stdio()

    print(f"OLLAMA_BASE={base}", flush=True)
    print(f"models={models} rounds={args.rounds}", flush=True)
    try:
        ver = get_json(base + "/api/version", timeout=15)
        print(f"api/version: {ver}", flush=True)
    except Exception as e:
        print(f"无法连接 {base}: {e}", file=sys.stderr)
        return 1

    results: dict[str, Any] = {
        "ollama_base": base,
        "version": ver,
        "models": models,
        "rounds": args.rounds,
        "runs": [],
    }

    for round_idx in range(1, args.rounds + 1):
        run_items: list[dict[str, Any]] = []
        for item in AXIS_PROMPTS:
            per_model: dict[str, Any] = {}
            for model in models:
                try:
                    text, elapsed_ms = chat(base, model, item.prompt, timeout=args.timeout)
                    per_model[model] = {"content": text, "elapsed_ms": elapsed_ms, "error": None}
                except Exception as e:
                    per_model[model] = {"content": "", "elapsed_ms": 0, "error": str(e)}
            run_items.append(
                {
                    "id": item.id,
                    "axis_zh": item.axis_zh,
                    "prompt": item.prompt,
                    "by_model": per_model,
                }
            )
            print(f"[r{round_idx}] {item.id} done", flush=True)
        results["runs"].append({"round": round_idx, "items": run_items})

    if args.output_json:
        path = os.path.abspath(args.output_json)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"Wrote JSON: {path}", flush=True)

    if args.output_md:
        path = os.path.abspath(args.output_md)
        lines: list[str] = []
        lines.append("# 多维度 Ollama 对比报告\n")
        lines.append(f"- **Base**: `{base}`\n")
        lines.append(f"- **Version**: `{results.get('version')}`\n")
        lines.append(f"- **Models**: {', '.join(models)}\n")
        lines.append(f"- **Rounds**: {args.rounds}\n")
        lines.append("\n---\n")
        for run in results["runs"]:
            r = run["round"]
            lines.append(f"\n## Round {r}\n")
            for it in run["items"]:
                lines.append(f"\n### {it['id']} — {it['axis_zh']}\n")
                lines.append("\n**Prompt（摘要）**\n\n")
                p = it["prompt"]
                lines.append("```text\n" + (p if len(p) < 800 else p[:800] + "\n…") + "\n```\n")
                for m in models:
                    bm = it["by_model"].get(m) or {}
                    err = bm.get("error")
                    ms = bm.get("elapsed_ms")
                    lines.append(f"\n#### `{m}` ({ms} ms" + (f", ERROR: {err}" if err else "") + ")\n\n")
                    content = bm.get("content") or ""
                    lines.append("```text\n" + content + "\n```\n")
        with open(path, "w", encoding="utf-8") as f:
            f.write("".join(lines))
        print(f"Wrote Markdown: {path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
