#!/usr/bin/env python3
"""
在能访问 Ollama HTTP 的机器上执行：拉取（若缺）qwen3:14b、gemma3:12b，并对主用模型等做同一提示词对比。

显存参考：RTX 5070 Ti ≈ 16GB → 拉取 qwen3:14b、gemma3:12b；不拉 27B（易 OOM）。

用法（在 Ollama 所在机或能访问其端口的机器上）：
  export OLLAMA_BASE=http://127.0.0.1:22545   # 或 http://ccnode.briconbric.com:22545
  python3 scripts/ollama_pull_and_benchmark.py

仅跑对比（不 pull）：
  python3 scripts/ollama_pull_and_benchmark.py --chat-only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = os.environ.get("OLLAMA_BASE", "http://127.0.0.1:11434")

PROMPT = (
    "请用简体中文回答：以下英文人名在中文新闻里的常见译名是什么？只写译名，一行一个：\n"
    "1. Donald Trump\n2. Taylor Swift\n3. Volodymyr Zelenskyy\n4. Sanae Takaichi"
)

MODELS = ["qwen3:14b", "gemma3:12b"]
PULL = ["qwen3:14b", "gemma3:12b"]


def _ensure_utf8_stdio() -> None:
    """避免 Windows 默认 cp932 下 print 中文段落触发 UnicodeEncodeError。"""
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


def pull_stream(base: str, name: str, max_sec: int = 3600) -> None:
    url = base.rstrip("/") + "/api/pull"
    body = json.dumps({"name": name}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=max_sec) as r:
        while True:
            line = r.readline()
            if not line:
                break
            try:
                j = json.loads(line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            status = j.get("status") or j.get("error") or str(j)
            print(f"  [{name}] {status}", flush=True)


def chat(base: str, model: str) -> str:
    url = base.rstrip("/") + "/api/chat"
    body: dict = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": False,
    }
    # Qwen3 系：关闭 thinking，避免 /api/chat 里混入长段推理（见 Ollama Thinking 文档）
    if model.lower().startswith("qwen3"):
        body["think"] = False
    out = post_json(url, body, timeout=600)
    msg = out.get("message") or {}
    return msg.get("content") or json.dumps(out, ensure_ascii=False)[:2000]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chat-only", action="store_true", help="不 pull，只跑三条 chat")
    ap.add_argument("--base", default=os.environ.get("OLLAMA_BASE", DEFAULT_BASE))
    ap.add_argument(
        "--output",
        metavar="FILE",
        help="将各模型输出写入 UTF-8 文本（与控制台无关，便于留存）",
    )
    args = ap.parse_args()
    base = args.base.rstrip("/")

    _ensure_utf8_stdio()

    print(f"OLLAMA_BASE={base}", flush=True)
    try:
        ver = get_json(base + "/api/version", timeout=15)
        print(f"api/version: {ver}", flush=True)
    except Exception as e:
        print(f"无法连接 {base}: {e}", file=sys.stderr)
        return 1

    if not args.chat_only:
        for name in PULL:
            print(f"\n=== pull {name} ===", flush=True)
            try:
                pull_stream(base, name)
                print(f"=== pull {name} done ===", flush=True)
            except urllib.error.HTTPError as e:
                print(f"pull failed: {e.read().decode()}", file=sys.stderr)
                return 1
            except Exception as e:
                print(f"pull failed: {e}", file=sys.stderr)
                return 1

    print("\n=== 同一提示词对比 ===\n", flush=True)
    lines_out: list[str] = []
    for model in MODELS:
        print(f"--- {model} ---", flush=True)
        lines_out.append(f"--- {model} ---")
        try:
            text = chat(base, model)
            print(text.strip(), flush=True)
            lines_out.append(text.strip())
        except Exception as e:
            err = f"ERROR: {e}"
            print(err, flush=True)
            lines_out.append(err)
        print(flush=True)
        lines_out.append("")

    if args.output:
        out_path = os.path.abspath(args.output)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("PROMPT:\n")
            f.write(PROMPT)
            f.write("\n\nRESULTS:\n")
            f.write("\n".join(lines_out))
        print(f"Wrote UTF-8 results to: {out_path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
