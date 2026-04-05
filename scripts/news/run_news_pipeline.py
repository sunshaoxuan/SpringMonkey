#!/usr/bin/env python3
"""
新闻多阶段流水线（管理者工具）：编排 → 工人落盘 → 合并 → 终稿 + 机械校验。

阶段概览
--------
1. plan          从 broadcast.json + job 名生成 plan.json（按地区拆批，与 1–4 大纲对齐）。
2. orchestrate   调用 OpenAI 兼容 API（默认 Codex/配置中的 newsOrchestrator）生成本批检索计划 orchestration.json。
3. worker        每批调用 Ollama（newsWorker）整理/筛选，写入 worker_<id>.md。
4. merge         拼接为 draft_merged.md。
5. finalize      再次调用 OpenAI 兼容 API，合并润色为 final_broadcast.md 并强调编号规则。
6. verify        调用 verify_broadcast_draft 规则做机械检查。

环境变量（常用）
--------------
OPENAI_API_KEY           编排与终稿（缺省则 orchestrate/finalize 用模板或跳过终稿）
NEWS_OPENAI_BASE_URL     默认 https://api.openai.com/v1
NEWS_ORCHESTRATOR_MODEL  覆盖 broadcast.json model.newsOrchestrator
OLLAMA_HOST              若设置则优先于配置，作为 Ollama HTTP 基址
model.ollamaBaseUrl      broadcast.json 中工人模型 HTTP 基址（定时任务无 shell 环境时常用）
                         未设置且未设 OLLAMA_HOST 时回退 http://127.0.0.1:11434
NEWS_WORKER_MODEL        覆盖 broadcast.json model.newsWorker（可带 ollama/ 前缀，调用 API 时会自动剥掉）

不落盘 OpenAI Key；运行目录仅含中间稿与 JSON。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "news" / "broadcast.json"

# 与 formatRules.outline 顺序一致
BATCH_SPECS: list[dict[str, Any]] = [
    {"id": "japan", "pool_key": "japan"},
    {"id": "china", "pool_key": "china"},
    {"id": "world", "pool_key": "world"},
    {"id": "markets", "pool_key": None},
]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_ollama_base_url(cfg: dict) -> str:
    """工人阶段 Ollama HTTP 基址：环境变量优先，其次 model.ollamaBaseUrl / ollamaHost。"""
    env = os.environ.get("OLLAMA_HOST", "").strip()
    if env:
        return env.rstrip("/")
    mc = cfg.get("model") or {}
    for key in ("ollamaBaseUrl", "ollamaHost"):
        v = mc.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().rstrip("/")
    return "http://127.0.0.1:11434"


def ollama_api_model_name(model_id: str) -> str:
    """
    Ollama /api/chat 的 model 字段必须是裸名（如 qwen2.5:14b-instruct）。
    broadcast 里常与 OpenClaw 一致写成 ollama/qwen2.5:14b-instruct，需去掉 provider 前缀。
    """
    s = (model_id or "").strip()
    if s.lower().startswith("ollama/"):
        rest = s.split("/", 1)[1].strip()
        return rest if rest else s
    return s


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


def http_post_json(url: str, payload: dict, headers: dict[str, str], timeout: int) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} {url}: {err_body}") from e
    return json.loads(raw)


def openai_chat(
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    timeout: int,
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = http_post_json(url, payload, headers, timeout)
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"unexpected OpenAI response: {data!r}") from e


def ollama_chat(host: str, model: str, system: str, user: str, timeout: int) -> str:
    url = host.rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
    }
    data = http_post_json(url, payload, {"Content-Type": "application/json"}, timeout)
    try:
        return data["message"]["content"].strip()
    except KeyError as e:
        raise RuntimeError(f"unexpected Ollama response: {data!r}") from e


def job_spec(cfg: dict, name: str) -> dict:
    for j in cfg.get("jobs", []):
        if j.get("name") == name:
            return j
    raise SystemExit(f"unknown job name: {name}")


def build_plan(cfg: dict, job: dict) -> dict:
    fr = cfg["formatRules"]
    outline = fr["outline"]
    if len(outline) != len(BATCH_SPECS):
        raise SystemExit("BATCH_SPECS/outline length mismatch; update BATCH_SPECS")
    batches = []
    for spec, line in zip(BATCH_SPECS, outline, strict=True):
        pk = spec["pool_key"]
        pool = (cfg.get("sourcePolicy", {}).get("sourcePools") or {}).get(pk) if pk else []
        batches.append(
            {
                "id": spec["id"],
                "outline_line": line,
                "source_pool": pool or [],
            }
        )
    return {
        "version": 1,
        "job_name": job["name"],
        "window_label": job["windowLabel"],
        "window_hours": job["windowHours"],
        "title_line": fr.get("titleLine", "新闻简报"),
        "fallback_no_news": fr.get("fallbackNoMajorUpdateLine", "本节无合格新增新闻条目。"),
        "batches": batches,
    }


def template_orchestration(plan: dict) -> dict:
    out = []
    for b in plan["batches"]:
        pool = b.get("source_pool") or []
        hints = "、".join(pool[:6]) if pool else "权威通讯社与主流媒体"
        q = [
            f"{b['outline_line']} 重要新闻 {plan['window_label']}",
            f"{hints} 最新",
        ]
        out.append(
            {
                "id": b["id"],
                "queries": q,
                "outlet_hints": pool[:12],
            }
        )
    return {"version": 1, "batches": out, "source": "template"}


def orchestrate_with_openai(plan: dict, cfg: dict, api_key: str, base_url: str, model: str, timeout: int) -> dict:
    system = (
        "你是新闻采集编排员。只输出 JSON，不要 markdown 围栏。"
        "根据各批地区与信源池，为每批生成 3–8 条可执行的搜索查询（中英均可），"
        "以及 outlet_hints 字符串数组（媒体名）。"
    )
    user = json.dumps(
        {
            "window": plan["window_label"],
            "batches": plan["batches"],
            "instruction": '输出格式：{"batches":[{"id":"japan","queries":[],"outlet_hints":[]}]}，id 必须与输入一致。',
        },
        ensure_ascii=False,
    )
    raw = openai_chat(base_url, api_key, model, system, user, timeout)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()
    data = json.loads(raw)
    if "batches" not in data:
        raise RuntimeError("orchestration JSON missing batches")
    return {"version": 1, "batches": data["batches"], "source": "openai"}


def worker_system_prompt_per_query() -> str:
    """per-query 模式：每次只处理一个检索主题，输出 0-3 条结构化条目。"""
    return (
        "你是新闻条目整理助手。根据给定的一个检索主题，输出 0-3 条结构化新闻条目。\n"
        "【输出格式】\n"
        "每条格式固定为两行：\n"
        "• 一句话中文摘要（20-60字）\n"
        "链接：https://具体原文URL\n\n"
        "【规则】\n"
        "• 条目以「• 」（U+2022 圆点+空格）开头，禁止用 - 或任何数字编号\n"
        "• 无可靠链接的条目不写\n"
        "• 没有合格条目时输出空文本\n"
        "• 不要解释、不要前言后语，只输出条目"
    )


def worker_system_prompt_batch() -> str:
    """per-batch 模式（兼容旧流程）：处理整个地区批次。"""
    return (
        "你是新闻整理与质检助手。只输出 Markdown 正文片段，不要解释流程。\n"
        "【格式】\n"
        "• 条目以「• 」（U+2022 圆点+空格）开头，禁止用 - 或数字编号\n"
        "• 链接另起一行：链接：https://...\n"
        "• 无链接则不写该条\n"
        "• 无合格条目时只输出：• 本节无合格新增新闻条目。"
    )


def worker_user_prompt_per_query(
    query: str,
    window_label: str,
    outlet_hints: list[str],
    dry_run: bool,
) -> str:
    """per-query 模式：最小化输入，只给一个检索主题。"""
    parts = [
        f"检索主题：{query}",
        f"时间窗：{window_label}",
    ]
    if outlet_hints:
        parts.append(f"优先媒体：{'、'.join(outlet_hints[:4])}")
    if dry_run:
        parts.append("（干跑模式：输出 1 条占位条目，标注【干跑占位】，链接用 example.com）")
    return "\n".join(parts)


def worker_user_prompt_batch(
    plan: dict,
    batch_plan: dict,
    orch_batch: dict,
    dry_run: bool,
    rss_hints: list[str] | None = None,
) -> str:
    """per-batch 模式（兼容旧流程）。"""
    lines = [
        f"地区：{batch_plan['outline_line']}",
        f"时间窗：{plan['window_label']}",
        f"查询：{json.dumps(orch_batch.get('queries', []), ensure_ascii=False)}",
        f"媒体：{json.dumps(orch_batch.get('outlet_hints', []), ensure_ascii=False)}",
    ]
    if rss_hints:
        lines.append(f"RSS参考：{'；'.join(rss_hints[:3])}")
    lines.append("请整理候选条目。无法联网时列出应核查的主题，但不要伪造事实。")
    if dry_run:
        lines.append("（干跑模式：输出两条占位示例条目，标注【干跑占位】，链接用 example.com）")
    return "\n".join(lines)


def _run_worker_per_query(
    *,
    queries: list[str],
    outlet_hints: list[str],
    window_label: str,
    ollama_host: str,
    model: str,
    timeout: int,
    dry_run: bool,
    bid: str,
    fallback_line: str,
    max_input_chars: int,
) -> str:
    """per-query 模式：每个 query 独立调用 Qwen，保持超短上下文。"""
    if not queries:
        return f"• {fallback_line}\n"

    sys_prompt = worker_system_prompt_per_query()
    fragments: list[str] = []

    for i, query in enumerate(queries):
        user_p = worker_user_prompt_per_query(query, window_label, outlet_hints, dry_run)
        if len(user_p) > max_input_chars:
            user_p = user_p[:max_input_chars]
        try:
            result = ollama_chat(ollama_host, model, sys_prompt, user_p, timeout)
        except Exception as e:
            if dry_run:
                result = f"• 【干跑占位】query {i}: {query[:30]}\n链接：https://example.com\n"
                print(f"[pipeline] worker per-query {bid}[{i}] failed, dry-run stub: {e}", file=sys.stderr)
            else:
                print(f"[pipeline] worker per-query {bid}[{i}] failed: {e}", file=sys.stderr)
                continue
        cleaned = result.strip()
        if cleaned:
            fragments.append(cleaned)

    if not fragments:
        return f"• {fallback_line}\n"
    return "\n".join(fragments) + "\n"


def _finalize_template_example(plan: dict) -> str:
    """生成一份精确模板示例，用于 system prompt 和机械兜底。"""
    fr_outline = plan.get("_outline") or []
    bullet = plan.get("_bullet", "• ")
    lines = [plan["title_line"], plan["window_label"]]
    fallback = plan.get("fallback_no_news", "本节无合格新增新闻条目。")
    for sec in fr_outline:
        lines.append(sec)
        lines.append(f"{bullet}{fallback}")
    return "\n".join(lines)


def finalize_system_prompt(cfg: dict, plan: dict, retry_errors: list[str] | None = None) -> str:
    fr = cfg["formatRules"]
    outline = "\n".join(fr["outline"])
    plan_with_outline = {**plan, "_outline": fr["outline"], "_bullet": fr.get("contentBulletPrefix", "• ")}
    example = _finalize_template_example(plan_with_outline)

    base = (
        "你是主编，负责合并工人草稿并输出最终 Discord 新闻简报。\n"
        "只输出最终成稿 Markdown，不要前言后语、不要解释、不要代码围栏。\n\n"
        "【强制版式（违反任何一条即为失败）】\n"
        f"第 1 行必须是：{plan['title_line']}\n"
        f"第 2 行必须是：{plan['window_label']}\n"
        "从第 3 行开始，必须按顺序且仅出现以下四个编号小节：\n"
        f"{outline}\n"
        "全文只允许上面这四行使用数字编号；其他任何地方不得出现数字编号。\n"
        "【禁止的编号形式举例】1. xxx / 2. xxx / 1、xxx / (1) xxx / ① xxx\n"
        "以上在条目行内全部禁止。\n"
        "一级标题必须加粗（用 ** 包裹），如 **1. 日本**。\n"
        "每个小节内条目一律用「• 」（Unicode 圆点 U+2022 + 空格）开头。\n"
        "不要使用短横线 - 作为条目符号（Discord 会错误渲染）。\n"
        f"若某节工人未提供合格条目，写一条「• {plan['fallback_no_news']}」。\n"
        "链接规则：每条新闻下另起一行「链接：https://...」；无链则不写该条。\n\n"
        "【模板示例（内容替换为工人实际条目）】\n"
        f"{example}\n"
    )
    if retry_errors:
        base += (
            "\n⚠ 上一次输出未通过校验，具体错误：\n"
            + "\n".join(f"  - {e}" for e in retry_errors)
            + "\n请严格修正后重新输出完整成稿。\n"
        )
    return base


def _strip_item_numbering(line: str) -> str:
    """
    去掉条目行首各种数字编号，只保留「- 」开头的纯项目符号形式。
    处理：- 1. xxx / - **1.** xxx / - 1、xxx / - (1) xxx / - ① xxx / 1. xxx（无-）
    """
    import re as _re

    s = line.strip()
    if s.startswith("- "):
        body = s[2:].lstrip()
        body = _re.sub(r"^\*{1,2}(\d+[\.\)）])\*{1,2}\s*", "", body)
        body = _re.sub(r"^(\d+)[\.\)）、，]\s*", "", body)
        body = _re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*", "", body)
        body = _re.sub(r"^\(\d+\)\s*", "", body)
        return "- " + body if body else s
    s = _re.sub(r"^\d+[\.\)）、，]\s*", "", s)
    s = _re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*", "", s)
    s = _re.sub(r"^\(\d+\)\s*", "", s)
    return s


def _mechanical_fallback(cfg: dict, plan: dict, merged_draft: str) -> str:
    """
    不依赖 LLM，纯机械拼接出 100% 通过 verify 的播报稿。
    按 batch 注释 (<!-- batch:xxx -->) 切分工人草稿，对应到 outline 四节；
    内容不做润色，但保证标题、时间窗、一级编号完全正确。
    """
    fr = cfg["formatRules"]
    outline: list[str] = fr.get("outline", [])
    fallback_line = plan.get("fallback_no_news", "本节无合格新增新闻条目。")

    bullet = fr.get("contentBulletPrefix", "• ")

    batch_ids = [b["id"] for b in plan.get("batches", [])]
    batch_content: dict[str, list[str]] = {bid: [] for bid in batch_ids}

    import re as _re

    current_bid: str | None = None
    for line in merged_draft.splitlines():
        m = _re.match(r"<!--\s*batch:(\w+)\s*-->", line)
        if m:
            current_bid = m.group(1)
            continue
        if current_bid and current_bid in batch_content:
            stripped = line.strip()
            if stripped:
                stripped = _strip_item_numbering(stripped)
                # 统一条目前缀：去掉 - / • 再加 bullet
                if stripped.startswith("- "):
                    stripped = stripped[2:].lstrip()
                elif stripped.startswith("• "):
                    stripped = stripped[2:].lstrip()
                if stripped:
                    stripped = f"{bullet}{stripped}"
                    batch_content[current_bid].append(stripped)

    result_lines = [plan["title_line"], plan["window_label"]]
    for i, sec_title in enumerate(outline):
        result_lines.append(sec_title)
        bid = batch_ids[i] if i < len(batch_ids) else None
        items = batch_content.get(bid, []) if bid else []
        if items:
            result_lines.extend(items)
        else:
            result_lines.append(f"{bullet}{fallback_line}")

    return "\n".join(result_lines) + "\n"


def merge_workers(run_dir: Path, plan: dict) -> str:
    parts = []
    for b in plan["batches"]:
        bid = b["id"]
        p = run_dir / f"worker_{bid}.md"
        if not p.is_file():
            raise SystemExit(f"missing worker file: {p}")
        parts.append(f"<!-- batch:{bid} -->\n{p.read_text(encoding='utf-8').strip()}\n")
    return "\n".join(parts).strip() + "\n"


def load_verify_text():
    path = Path(__file__).resolve().parent / "verify_broadcast_draft.py"
    spec = importlib.util.spec_from_file_location("verify_broadcast_draft", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load verify_broadcast_draft")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.verify_text


def main() -> int:
    parser = argparse.ArgumentParser(description="新闻多阶段流水线（Codex 编排/终稿 + Qwen 工人落盘）")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--job", required=True, help="jobs.json 中的 name，如 news-digest-jst-1700")
    parser.add_argument("--run-dir", type=Path, help="运行目录；默认 repo 下 var/news-runs/<ts>_<job>")
    parser.add_argument("--dry-run", action="store_true", help="工人输出占位；编排/终稿仍尽量走 API（若无 Key 用模板）")
    parser.add_argument("--template-orchestrate", action="store_true", help="跳过 Codex 编排，只用模板检索计划")
    parser.add_argument("--skip-finalize", action="store_true", help="不调用主编模型，draft 即结束")
    parser.add_argument("--skip-worker", action="store_true", help="不调用 Ollama，写入占位 worker_*.md（测合并/终稿）")
    parser.add_argument("--skip-verify", action="store_true", help="跳过机械校验")
    parser.add_argument("--openai-timeout", type=int, default=120)
    parser.add_argument("--ollama-timeout", type=int, default=300)
    args = parser.parse_args()

    cfg = load_json(args.config)
    sp = cfg.get("sourcePolicy") or {}
    raw_hints = sp.get("rssFeedHints")
    if isinstance(raw_hints, list):
        rss_hints = [str(x).strip() for x in raw_hints if str(x).strip()]
    else:
        rss_hints = []
    job = job_spec(cfg, args.job)
    model_cfg = cfg.get("model", {})
    orch_model = os.environ.get(
        "NEWS_ORCHESTRATOR_MODEL",
        model_cfg.get("newsOrchestrator", "gpt-4o"),
    )
    worker_model = os.environ.get(
        "NEWS_WORKER_MODEL",
        model_cfg.get("newsWorker", "qwen2.5:14b-instruct"),
    )
    ollama_worker_model = ollama_api_model_name(worker_model)
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get("NEWS_OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    ollama_host = resolve_ollama_base_url(cfg)

    ts = int(time.time())
    run_dir = args.run_dir
    if not run_dir:
        run_dir = REPO_ROOT / "var" / "news-runs" / f"{ts}_{args.job}"
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    plan = build_plan(cfg, job)
    save_json(run_dir / "plan.json", plan)
    save_json(
        run_dir / "meta.json",
        {
            "created_at_ts": ts,
            "job": args.job,
            "dry_run": args.dry_run,
            "orchestrator_model": orch_model,
            "worker_model": worker_model,
            "worker_call_mode": model_cfg.get("workerCallMode", "per-batch"),
            "ollama_api_model": ollama_worker_model,
            "ollama_base_url": ollama_host,
        },
    )

    # --- orchestrate ---
    if args.template_orchestrate or not api_key:
        orch = template_orchestration(plan)
    else:
        try:
            orch = orchestrate_with_openai(
                plan, cfg, api_key, base_url, orch_model, args.openai_timeout
            )
        except Exception as e:
            print(f"[pipeline] orchestrate fallback template: {e}", file=sys.stderr)
            orch = template_orchestration(plan)
    tpl = template_orchestration(plan)
    tpl_by_id = {b["id"]: b for b in tpl["batches"]}
    orch_by_id = {b["id"]: b for b in orch.get("batches", [])}
    for b in plan["batches"]:
        if b["id"] not in orch_by_id:
            print(
                f"[pipeline] orchestration missing batch {b['id']}, using template slice",
                file=sys.stderr,
            )
            orch_by_id[b["id"]] = tpl_by_id[b["id"]]
    orch["batches"] = [orch_by_id[b["id"]] for b in plan["batches"]]
    save_json(run_dir / "orchestration.json", orch)

    # --- workers ---
    worker_call_mode = model_cfg.get("workerCallMode", "per-batch")
    max_worker_chars = int(model_cfg.get("maxWorkerInputChars", 1500))
    fallback_text_tpl = plan["fallback_no_news"]

    for b in plan["batches"]:
        bid = b["id"]
        out_path = run_dir / f"worker_{bid}.md"
        if args.skip_worker:
            out_path.write_text(
                f"• 【skip-worker】{b['outline_line']} 占位草稿。\n",
                encoding="utf-8",
            )
            continue
        ob = orch_by_id.get(bid) or {"id": bid, "queries": [], "outlet_hints": []}

        if worker_call_mode == "per-query":
            text = _run_worker_per_query(
                queries=ob.get("queries", []),
                outlet_hints=ob.get("outlet_hints", []),
                window_label=plan["window_label"],
                ollama_host=ollama_host,
                model=ollama_worker_model,
                timeout=args.ollama_timeout,
                dry_run=args.dry_run,
                bid=bid,
                fallback_line=fallback_text_tpl,
                max_input_chars=max_worker_chars,
            )
        else:
            sys_prompt = worker_system_prompt_batch()
            user_p = worker_user_prompt_batch(plan, b, ob, args.dry_run, rss_hints or None)
            if len(user_p) > max_worker_chars:
                print(
                    f"[pipeline] warning: worker input for {bid} is {len(user_p)} chars "
                    f"(max {max_worker_chars}), consider per-query mode",
                    file=sys.stderr,
                )
            try:
                text = ollama_chat(
                    ollama_host, ollama_worker_model, sys_prompt, user_p, args.ollama_timeout
                )
            except Exception as e:
                if args.dry_run:
                    text = f"• 【干跑】工人失败回退：{bid}\n• {fallback_text_tpl}\n"
                    print(f"[pipeline] ollama worker {bid} failed, dry-run stub: {e}", file=sys.stderr)
                else:
                    raise
        out_path.write_text(text.strip() + "\n", encoding="utf-8")

    # --- merge ---
    draft = merge_workers(run_dir, plan)
    (run_dir / "draft_merged.md").write_text(draft, encoding="utf-8")

    # --- finalize (with verify-retry loop) ---
    final_path = run_dir / "final_broadcast.md"
    max_finalize_attempts = 3

    if args.skip_finalize:
        final_path.write_text(draft, encoding="utf-8")
        print(f"PIPELINE_OK skip_finalize -> {final_path}")
        return 0

    if not api_key:
        print("[pipeline] no OPENAI_API_KEY: using mechanical template fallback", file=sys.stderr)

    verify_text_fn = load_verify_text() if not args.skip_verify else None
    last_errors: list[str] = []

    for attempt in range(1, max_finalize_attempts + 1):
        if not api_key:
            final_text = _mechanical_fallback(cfg, plan, draft)
        else:
            fin_sys = finalize_system_prompt(cfg, plan, last_errors if attempt > 1 else None)
            fin_user = "工人合并草稿如下，请输出最终成稿：\n\n" + draft
            final_text = openai_chat(
                base_url, api_key, orch_model, fin_sys, fin_user, args.openai_timeout * 2
            )
        final_text = final_text.strip() + "\n"
        final_path.write_text(final_text, encoding="utf-8")

        if verify_text_fn is None:
            break
        ok, errors = verify_text_fn(final_text, cfg)
        if ok:
            print(f"[pipeline] finalize attempt {attempt}/{max_finalize_attempts}: VERIFY_OK")
            break
        last_errors = errors
        print(
            f"[pipeline] finalize attempt {attempt}/{max_finalize_attempts}: VERIFY_FAIL {errors}",
            file=sys.stderr,
        )
        save_json(run_dir / f"verify_errors_attempt{attempt}.json", {"errors": errors})
    else:
        print("[pipeline] all finalize attempts failed; applying mechanical template fallback", file=sys.stderr)
        fallback_text = _mechanical_fallback(cfg, plan, draft)
        final_path.write_text(fallback_text, encoding="utf-8")
        if verify_text_fn:
            ok2, err2 = verify_text_fn(fallback_text, cfg)
            if not ok2:
                print("VERIFY_DRAFT_FAIL (even mechanical fallback)", file=sys.stderr)
                for e in err2:
                    print(e, file=sys.stderr)
                save_json(run_dir / "verify_errors.json", {"errors": err2})
                return 3

    print("PIPELINE_OK", run_dir)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
