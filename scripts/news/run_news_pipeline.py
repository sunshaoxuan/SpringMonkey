#!/usr/bin/env python3
"""
新闻多阶段流水线：RSS 发现 → HTTP 取回 → Qwen 逐条总结 → GPT-OSS 终稿 → 机械校验。

阶段概览
--------
1. plan          从 broadcast.json + job 名生成 plan.json（按地区拆批，与 1–4 大纲对齐）。
2. discover      RSS 抓取各地区新闻源，获取真实文章链接（无需 API key）。
3. fetch         HTTP 取回每篇文章正文内容。
4. worker        每篇文章独立调用 Qwen（Ollama），输入真实正文 → 输出中文摘要+保留原链接。
5. merge         拼接为 draft_merged.md。
6. finalize      GPT-OSS（本地 Ollama 20b，可靠）合并润色 → Codex API 降级备选 → 机械兜底。
7. verify        调用 verify_broadcast_draft 规则做机械检查。

模型分工
--------
- Qwen (qwen3:14b)  → 逐条处理器：短上下文、单篇文章摘要
- GPT-OSS (gpt-oss:20b)        → 终稿格式化：本地可靠，无超量风险
- Codex (openai-codex/gpt-5.4) → 降级备选：有超量拒绝风险

环境变量（常用）
--------------
OPENAI_API_KEY           降级用 Codex 编排/终稿（缺省则全走本地模型+机械兜底）
OLLAMA_HOST              若设置则优先于配置，作为 Ollama HTTP 基址
model.ollamaBaseUrl      broadcast.json 中 Ollama 基址
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from staged_jobs.task_trace import StagedTaskTrace


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "news" / "broadcast.json"
NEWS_STATE_DIR = Path("/var/lib/openclaw/.openclaw/state/news")
RECENT_ITEMS_PATH = NEWS_STATE_DIR / "recent_items.json"

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
    Ollama /api/chat 的 model 字段必须是裸名（如 qwen3:14b）。
    broadcast 里常与 OpenClaw 一致写成 ollama/qwen3:14b，需去掉 provider 前缀。
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


def load_recent_items(path: Path, now_ts: int, max_age_hours: int) -> dict[str, Any]:
    try:
        data = load_json(path)
    except Exception:
        return {"version": 1, "items": []}
    cutoff = now_ts - max_age_hours * 3600
    kept = []
    for item in data.get("items", []):
        seen_ts = int(item.get("seen_ts") or 0)
        if seen_ts >= cutoff:
            kept.append(item)
    return {"version": 1, "items": kept}


def append_recent_items(path: Path, data: dict[str, Any], articles: list[dict], now_ts: int) -> None:
    items = list(data.get("items", []))
    seen = {str(item.get("fingerprint") or "") for item in items}
    for art in articles:
        fp = str(art.get("fingerprint") or "")
        if not fp or fp in seen:
            continue
        seen.add(fp)
        items.append(
            {
                "fingerprint": fp,
                "title": art.get("title", ""),
                "url": art.get("url", ""),
                "published_ts": int(art.get("published_ts") or 0),
                "seen_ts": now_ts,
            }
        )
    save_json(path, {"version": 1, "items": items})


def compute_window_bounds(job: dict, tz_name: str) -> tuple[int, int]:
    schedule = job.get("schedule") or {}
    expr = str(schedule.get("expr") or "").strip()
    hour = 0
    minute = 0
    parts = expr.split()
    if len(parts) >= 2:
        minute = int(parts[0])
        hour = int(parts[1])
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)
    end_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if end_local > now_local:
        end_local -= timedelta(days=1)
    end_ts = int(end_local.timestamp())
    start_ts = end_ts - int(job.get("windowHours") or 0) * 3600
    return start_ts, end_ts


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
        "_outline": outline,
        "_format_rules": fr,
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


SUMMARIZE_SYSTEM_PROMPT = (
    "你是新闻摘要助手。根据给定的原文内容，输出一条中文摘要。\n"
    "【输出格式（严格两行）】\n"
    "• 一句话中文摘要（20-60字，概括核心事实）\n"
    "链接：{url}\n\n"
    "【规则】\n"
    "• 以「• 」（U+2022 圆点+空格）开头\n"
    "• 只输出摘要和链接，不要解释、不要前言后语\n"
    "• 如果原文内容无实质新闻价值，输出空文本"
)


def summarize_article_prompt(title: str, url: str, content: str, max_chars: int = 1500) -> tuple[str, str]:
    """为单篇文章生成 Qwen 调用的 system/user prompt。"""
    sys_p = SUMMARIZE_SYSTEM_PROMPT.replace("{url}", url)
    body = content[:max_chars] if len(content) > max_chars else content
    user_p = f"标题：{title}\n链接：{url}\n\n正文：\n{body}"
    return sys_p, user_p


def deterministic_summary_from_article(title: str, url: str) -> str:
    """模型摘要失败时的最小可用兜底（保留来源链接）。"""
    title_clean = " ".join((title or "").split()).strip()
    if len(title_clean) > 120:
        title_clean = title_clean[:117] + "..."
    if not title_clean:
        title_clean = "本条新闻来源可用，但摘要模型未返回有效文本。"
    return f"• {title_clean}\n链接：{url}"


def strip_think_blocks(text: str) -> str:
    """移除模型可能泄漏的 <think>...</think> 思维链块。"""
    if not text:
        return ""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    return cleaned.strip()


def _summarize_articles_with_qwen(
    articles: list[dict],
    ollama_host: str,
    model: str,
    timeout: int,
    fallback_line: str,
    max_input_chars: int,
    bid: str,
) -> str:
    """逐篇文章调用 Qwen 做摘要，每次超短上下文。"""
    if not articles:
        return f"• {fallback_line}\n"

    fragments: list[str] = []
    for i, art in enumerate(articles):
        if not art.get("content") or not art.get("fetch_ok"):
            continue
        sys_p, user_p = summarize_article_prompt(
            art["title"], art["url"], art["content"], max_input_chars
        )
        try:
            result = ollama_chat(ollama_host, model, sys_p, user_p, timeout)
        except Exception as e:
            print(f"[pipeline] summarize {bid}[{i}] failed: {e}", file=sys.stderr)
            fragments.append(deterministic_summary_from_article(art["title"], art["url"]))
            continue
        cleaned = strip_think_blocks(result)
        if cleaned and not cleaned.startswith("[") and len(cleaned) > 10:
            fragments.append(cleaned)
        else:
            fragments.append(deterministic_summary_from_article(art["title"], art["url"]))

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
    """合并 worker 输出为已格式化的完整草稿（标题+时间窗+小节标题+内容）。"""
    fr = plan.get("_format_rules") or {}
    bullet = fr.get("contentBulletPrefix", "• ")
    fallback = plan.get("fallback_no_news", "本节无合格新增新闻条目。")
    outline = plan.get("_outline") or []

    lines = [plan["title_line"], plan["window_label"]]
    for i, b in enumerate(plan["batches"]):
        bid = b["id"]
        p = run_dir / f"worker_{bid}.md"
        if not p.is_file():
            raise SystemExit(f"missing worker file: {p}")
        content = p.read_text(encoding="utf-8").strip()

        header = outline[i] if i < len(outline) else b.get("outline_line", f"{i+1}. {bid}")
        lines.append(header)

        if content and not content.startswith("•") and not content.startswith(bullet):
            for cline in content.splitlines():
                cline = cline.strip()
                if cline:
                    lines.append(cline)
        elif content:
            lines.append(content)
        else:
            lines.append(f"{bullet}{fallback}")

    return "\n".join(lines).strip() + "\n"


def load_verify_text():
    path = Path(__file__).resolve().parent / "verify_broadcast_draft.py"
    spec = importlib.util.spec_from_file_location("verify_broadcast_draft", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load verify_broadcast_draft")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.verify_text


def _load_fetcher():
    path = Path(__file__).resolve().parent / "news_fetcher.py"
    spec = importlib.util.spec_from_file_location("news_fetcher", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load news_fetcher")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["news_fetcher"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    parser = argparse.ArgumentParser(description="新闻流水线：RSS发现 → HTTP取回 → Qwen逐条总结 → GPT-OSS终稿")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--job", required=True, help="jobs.json 中的 name，如 news-digest-jst-1700")
    parser.add_argument("--run-dir", type=Path, help="运行目录；默认 repo 下 var/news-runs/<ts>_<job>")
    parser.add_argument("--dry-run", action="store_true", help="跳过真实搜索/抓取，用占位数据")
    parser.add_argument("--skip-discover", action="store_true", help="跳过 RSS 发现阶段")
    parser.add_argument("--skip-fetch", action="store_true", help="跳过正文抓取")
    parser.add_argument("--skip-finalize", action="store_true", help="不调用终稿模型，draft 即结束")
    parser.add_argument("--skip-worker", action="store_true", help="不调用 Qwen，写入占位 worker_*.md")
    parser.add_argument("--skip-verify", action="store_true", help="跳过机械校验")
    parser.add_argument("--openai-timeout", type=int, default=120)
    parser.add_argument("--ollama-timeout", type=int, default=300)
    args = parser.parse_args()

    cfg = load_json(args.config)
    job = job_spec(cfg, args.job)
    model_cfg = cfg.get("model", {})

    worker_model_raw = os.environ.get(
        "NEWS_WORKER_MODEL",
        model_cfg.get("newsWorker", "qwen3:14b"),
    )
    finalize_model_raw = model_cfg.get("newsFinalize", "gpt-oss:20b")
    orch_model = os.environ.get(
        "NEWS_ORCHESTRATOR_MODEL",
        model_cfg.get("newsOrchestrator", "ollama/qwen3:14b"),
    )

    ollama_worker_model = ollama_api_model_name(worker_model_raw)
    ollama_finalize_model = ollama_api_model_name(finalize_model_raw)
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get("NEWS_OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    ollama_host = resolve_ollama_base_url(cfg)
    max_worker_chars = int(model_cfg.get("maxWorkerInputChars", 1500))
    dedupe_hours = int((cfg.get("newsExecution") or {}).get("crossRunDedupeHours", 36))
    require_timestamp = bool((cfg.get("newsExecution") or {}).get("requireTimestampInWindow", True))

    ts = int(time.time())
    run_dir = args.run_dir
    if not run_dir:
        run_dir = REPO_ROOT / "var" / "news-runs" / f"{ts}_{args.job}"
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    trace = StagedTaskTrace(args.job, "news")
    trace.start("build-plan")

    plan = build_plan(cfg, job)
    window_start_ts, window_end_ts = compute_window_bounds(job, cfg.get("timezone", "Asia/Tokyo"))
    save_json(run_dir / "plan.json", plan)
    trace.artifact("run_dir", str(run_dir))
    trace.artifact("window_label", job["windowLabel"])
    trace.step("build-plan", "ok", detail=f"batches={len(plan['batches'])}", tool="planner")
    save_json(
        run_dir / "meta.json",
        {
            "created_at_ts": ts,
            "job": args.job,
            "dry_run": args.dry_run,
            "worker_model": worker_model_raw,
            "finalize_model": finalize_model_raw,
            "orchestrator_model": orch_model,
            "worker_call_mode": "per-article",
            "ollama_api_worker": ollama_worker_model,
            "ollama_api_finalize": ollama_finalize_model,
            "ollama_base_url": ollama_host,
            "window_start_ts": window_start_ts,
            "window_end_ts": window_end_ts,
            "cross_run_dedupe_hours": dedupe_hours,
            "require_timestamp_in_window": require_timestamp,
        },
    )

    fallback_text_tpl = plan["fallback_no_news"]

    # --- discover + fetch ---
    fetcher = _load_fetcher()
    trace.step("load-fetcher", "ok", detail="news_fetcher loaded", tool="python")
    all_articles: dict[str, list] = {}
    NEWS_STATE_DIR.mkdir(parents=True, exist_ok=True)
    recent_items = load_recent_items(RECENT_ITEMS_PATH, ts, dedupe_hours)
    seen_fingerprints = {
        str(item.get("fingerprint") or "")
        for item in recent_items.get("items", [])
        if str(item.get("fingerprint") or "")
    }

    for b in plan["batches"]:
        bid = b["id"]
        if args.skip_discover or args.dry_run:
            all_articles[bid] = []
            trace.step("discover", "skipped", detail=bid, tool="rss")
            continue
        print(f"[pipeline] discover {bid}...", file=sys.stderr)
        trace.step("discover", "running", detail=bid, tool="rss")
        articles = fetcher.discover_articles(
            bid,
            max_per_batch=8,
            window_start_ts=window_start_ts,
            window_end_ts=window_end_ts,
            exclude_fingerprints=seen_fingerprints,
            require_timestamp=require_timestamp,
        )
        if not args.skip_fetch:
            print(f"[pipeline] fetch {bid}: {len(articles)} articles...", file=sys.stderr)
            trace.step("fetch", "running", detail=f"{bid}: {len(articles)} articles", tool="http")
            fetcher.fetch_and_fill(articles, max_chars=max_worker_chars)
        all_articles[bid] = [
            {
                "title": a.title,
                "url": a.url,
                "content": a.content,
                "fetch_ok": a.fetch_ok,
                "snippet": a.snippet,
                "published_at": a.published_at,
                "published_ts": a.published_ts,
                "fingerprint": a.fingerprint,
            }
            for a in articles
        ]
        for art in all_articles[bid]:
            fp = str(art.get("fingerprint") or "")
            if fp:
                seen_fingerprints.add(fp)
        save_json(run_dir / f"articles_{bid}.json", all_articles[bid])
        trace.step(
            "discover-fetch",
            "ok",
            detail=f"{bid}: discovered {len(articles)} articles, fetched {len([a for a in all_articles[bid] if a.get('fetch_ok')])}",
            tool="rss+http",
        )

    # --- worker: Qwen 逐条总结 ---
    for b in plan["batches"]:
        bid = b["id"]
        out_path = run_dir / f"worker_{bid}.md"
        if args.skip_worker:
            out_path.write_text(
                f"• 【skip-worker】{b['outline_line']} 占位草稿。\n",
                encoding="utf-8",
            )
            trace.step("worker", "skipped", detail=bid, tool="ollama")
            continue
        articles = all_articles.get(bid, [])
        if args.dry_run:
            text = f"• 【干跑占位】{b['outline_line']}\n链接：https://example.com\n"
        else:
            trace.step("worker", "running", detail=f"{bid}: {len(articles)} articles", tool=ollama_worker_model)
            text = _summarize_articles_with_qwen(
                articles=articles,
                ollama_host=ollama_host,
                model=ollama_worker_model,
                timeout=args.ollama_timeout,
                fallback_line=fallback_text_tpl,
                max_input_chars=max_worker_chars,
                bid=bid,
            )
        out_path.write_text(text.strip() + "\n", encoding="utf-8")
        trace.step("worker", "ok", detail=f"{bid}: wrote {out_path.name}", tool=ollama_worker_model)

    # --- merge (已格式化：标题+时间窗+小节标题+内容) ---
    draft = merge_workers(run_dir, plan)
    (run_dir / "draft_merged.md").write_text(draft, encoding="utf-8")
    trace.step("merge", "ok", detail="draft_merged.md ready", tool="merge")

    # --- finalize ---
    final_path = run_dir / "final_broadcast.md"
    verify_text_fn = load_verify_text() if not args.skip_verify else None

    if args.skip_finalize:
        final_path.write_text(draft, encoding="utf-8")
        trace.finish("ok", "skip-finalize", final_message=str(final_path))
        print(f"PIPELINE_OK skip_finalize -> {final_path}")
        return 0

    # 策略：merge 草稿已经包含完整格式，先直接校验；
    # 如果通过就直接用（省掉 finalize 模型调用）；
    # 不通过才走 GPT-OSS → mechanical fallback。
    if verify_text_fn:
        ok_draft, draft_errors = verify_text_fn(draft, cfg)
        if ok_draft:
            print("[pipeline] merged draft passes verify directly, skipping finalize model", file=sys.stderr)
            final_path.write_text(draft, encoding="utf-8")
            trace.step("verify", "ok", detail="merged draft passed verify directly", tool="verify")
            append_recent_items(
                RECENT_ITEMS_PATH,
                recent_items,
                [art for batch in all_articles.values() for art in batch if art.get("fetch_ok")],
                ts,
            )
            trace.finish("ok", "done", final_message=str(final_path))
            print("PIPELINE_OK", run_dir)
            return 0
        else:
            print(f"[pipeline] merged draft verify failed: {draft_errors}, trying finalize model", file=sys.stderr)

    max_finalize_attempts = 2
    last_errors: list[str] = []

    for attempt in range(1, max_finalize_attempts + 1):
        trace.step("finalize", "running", detail=f"attempt {attempt}", tool=ollama_finalize_model)
        fin_sys = finalize_system_prompt(cfg, plan, last_errors if attempt > 1 else None)
        fin_user = "以下是已格式化的合并草稿，只需微调格式即可输出最终成稿（不要改写内容或链接）：\n\n" + draft

        try:
            print(f"[pipeline] finalize attempt {attempt}: GPT-OSS ({ollama_finalize_model})...", file=sys.stderr)
            final_text = ollama_chat(
                ollama_host, ollama_finalize_model, fin_sys, fin_user, args.ollama_timeout
            )
        except Exception as e:
            print(f"[pipeline] GPT-OSS finalize failed: {e}", file=sys.stderr)
            if api_key:
                print(f"[pipeline] fallback to Codex ({orch_model})...", file=sys.stderr)
                try:
                    final_text = openai_chat(
                        base_url, api_key, orch_model, fin_sys, fin_user, args.openai_timeout * 2
                    )
                except Exception as e2:
                    print(f"[pipeline] Codex finalize also failed: {e2}", file=sys.stderr)
                    final_text = _mechanical_fallback(cfg, plan, draft)
            else:
                final_text = _mechanical_fallback(cfg, plan, draft)

        final_text = strip_think_blocks(final_text).strip() + "\n"
        final_path.write_text(final_text, encoding="utf-8")

        if verify_text_fn is None:
            break
        ok, errors = verify_text_fn(final_text, cfg)
        if ok:
            print(f"[pipeline] finalize attempt {attempt}/{max_finalize_attempts}: VERIFY_OK")
            trace.step("verify", "ok", detail=f"attempt {attempt}", tool="verify")
            break
        last_errors = errors
        print(
            f"[pipeline] finalize attempt {attempt}/{max_finalize_attempts}: VERIFY_FAIL {errors}",
            file=sys.stderr,
        )
        save_json(run_dir / f"verify_errors_attempt{attempt}.json", {"errors": errors})
        trace.step("verify", "failed", detail=f"attempt {attempt}: {errors}", tool="verify")
    else:
        print("[pipeline] finalize attempts failed; applying mechanical fallback", file=sys.stderr)
        fallback_text = _mechanical_fallback(cfg, plan, draft)
        final_path.write_text(fallback_text, encoding="utf-8")
        trace.step("finalize", "fallback", detail="mechanical fallback applied", tool="fallback")
        if verify_text_fn:
            ok2, err2 = verify_text_fn(fallback_text, cfg)
            if not ok2:
                print("VERIFY_DRAFT_FAIL (even mechanical fallback)", file=sys.stderr)
                for e in err2:
                    print(e, file=sys.stderr)
                save_json(run_dir / "verify_errors.json", {"errors": err2})
                trace.finish("failed", "verify-failed", final_message=str(err2))
                return 3

    append_recent_items(
        RECENT_ITEMS_PATH,
        recent_items,
        [art for batch in all_articles.values() for art in batch if art.get("fetch_ok")],
        ts,
    )
    trace.finish("ok", "done", final_message=str(final_path))
    print("PIPELINE_OK", run_dir)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
