#!/usr/bin/env python3
"""
新闻多阶段流水线：RSS 发现 → HTTP 取回 → Codex 逐条整理 → Codex 终稿 → 机械校验。

阶段概览
--------
1. plan          从 broadcast.json + job 名生成 plan.json（按地区拆批，与 1–4 大纲对齐）。
2. discover      RSS 抓取各地区新闻源，获取真实文章链接（无需 API key）。
3. fetch         HTTP 取回每篇文章正文内容。
4. worker        每篇文章独立调用 Codex 主模型，输入真实正文 → 输出中文摘要+保留原链接；Qwen/Ollama 仅兜底。
5. merge         拼接为 draft_merged.md。
6. finalize      Codex 主模型合并润色 → Qwen/Ollama 兜底 → 机械兜底。
7. verify        调用 verify_broadcast_draft 规则做机械检查。

模型分工
--------
- Codex (openai-codex/gpt-5.5) → 默认主模型：编排、逐条处理、终稿格式化
- Qwen (qwen3:14b)             → 兜底处理器：仅在 Codex 不可用时尝试

环境变量（常用）
--------------
OpenClaw Codex profile   Codex 主模型通过 OpenClaw gateway/OAuth profile 调用
NEWS_CODEX_BASE_URL      OpenAI-compatible Codex HTTP endpoint, e.g. http://ccnode.briconbric.com:49530/v1
NEWS_CODEX_API_KEY       API key for NEWS_CODEX_BASE_URL. Required when codexBaseUrl is configured.
OLLAMA_HOST              若设置则优先于配置，作为 Ollama HTTP 基址
model.ollamaBaseUrl      broadcast.json 中 Ollama 基址
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
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
PUBLISHED_ITEMS_PATH = NEWS_STATE_DIR / "published_items.json"
RUNTIME_ENV_FILES = [
    Path("/etc/openclaw/openclaw.env"),
    Path("/var/lib/openclaw/.openclaw/openclaw.env"),
]

# 与 formatRules.outline 顺序一致
BATCH_SPECS: list[dict[str, Any]] = [
    {"id": "japan", "pool_key": "japan"},
    {"id": "china", "pool_key": "china"},
    {"id": "us", "pool_key": "us"},
    {"id": "europe", "pool_key": "europe"},
    {"id": "ai", "pool_key": "ai"},
    {"id": "technology", "pool_key": "technology"},
    {"id": "entertainment", "pool_key": "entertainment"},
    {"id": "world", "pool_key": "world"},
    {"id": "markets", "pool_key": "markets"},
]

DEFAULT_NEWS_REGIONS = tuple(spec["id"] for spec in BATCH_SPECS)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_runtime_env_files(paths: list[Path] = RUNTIME_ENV_FILES) -> None:
    """Load shared host env files for direct cron tasks without overriding process env."""
    for path in paths:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            value = value.strip().strip('"').strip("'")
            os.environ[key] = value


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


def resolve_codex_base_url(cfg: dict) -> str:
    env = os.environ.get("NEWS_CODEX_BASE_URL", "").strip()
    if env:
        return env.rstrip("/")
    mc = cfg.get("model") or {}
    value = mc.get("codexBaseUrl")
    if isinstance(value, str) and value.strip():
        return value.strip().rstrip("/")
    return ""


def resolve_codex_api_key(cfg: dict) -> str:
    mc = cfg.get("model") or {}
    env_name = str(mc.get("codexApiKeyEnv") or "NEWS_CODEX_API_KEY").strip() or "NEWS_CODEX_API_KEY"
    for name in (
        env_name,
        "NEWS_CODEX_API_KEY",
        "OPENCLAW_CODEX_API_KEY",
        "CODEX_API_KEY",
        "OPENAI_CODEX_API_KEY",
        "OPENCLAW_PUBLIC_MODEL_API_KEY",
    ):
        value = os.environ.get(name, "").strip()
        if value:
            return value
        file_value = os.environ.get(f"{name}_FILE", "").strip()
        if file_value:
            try:
                secret = Path(file_value).read_text(encoding="utf-8").strip()
            except OSError:
                secret = ""
            if secret:
                return secret
    value = mc.get("codexApiKey")
    return value.strip() if isinstance(value, str) else ""


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


def provider_api_model_name(model_id: str) -> str:
    s = (model_id or "").strip()
    for prefix in ("openai-codex/", "openai/", "ollama/"):
        if s.lower().startswith(prefix):
            return s.split("/", 1)[1].strip() or s
    return s


def is_openai_model(model_id: str) -> bool:
    s = (model_id or "").strip().lower()
    return s.startswith("openai-codex/") or s.startswith("openai/")


def is_openclaw_codex_model(model_id: str) -> bool:
    return (model_id or "").strip().lower().startswith("openai-codex/")


def _extract_openclaw_model_text(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    json_start = text.find("{")
    if json_start >= 0:
        try:
            data = json.loads(text[json_start:])
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            for key in ("content", "text", "response", "output", "message"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
                if isinstance(value, dict):
                    nested = value.get("content") or value.get("text")
                    if isinstance(nested, str) and nested.strip():
                        return nested.strip()
            choices = data.get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                message = choices[0].get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    return message["content"].strip()
            outputs = data.get("outputs")
            if isinstance(outputs, list) and outputs and isinstance(outputs[0], dict):
                output_text = outputs[0].get("text")
                if isinstance(output_text, str) and output_text.strip():
                    return output_text.strip()
    lines = [
        line
        for line in text.splitlines()
        if line.strip()
        and not line.startswith("Config warnings:")
        and not line.startswith("- plugins:")
        and not line.startswith("🦞 OpenClaw")
    ]
    return "\n".join(lines).strip()


def openclaw_model_chat(model: str, system: str, user: str, timeout: int) -> str:
    prompt = "\n\n".join(["System instructions:", system, "User input:", user])
    cmd = [
        "openclaw",
        "infer",
        "model",
        "run",
        "--gateway",
        "--model",
        model,
        "--json",
        "--prompt",
        prompt,
    ]
    env = os.environ.copy()
    env.setdefault("HOME", "/var/lib/openclaw")
    attempts = max(1, int(os.environ.get("NEWS_OPENCLAW_INFER_RETRIES", "3")))
    last_detail = ""
    for attempt in range(1, attempts + 1):
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as e:
            last_detail = f"timeout after {timeout}s: {e}"
            if attempt < attempts:
                time.sleep(min(2 * attempt, 8))
                continue
            raise
        if proc.returncode == 0:
            content = _extract_openclaw_model_text(proc.stdout)
            if content:
                return content
            last_detail = f"empty response: {proc.stdout[-800:]}"
        else:
            last_detail = (proc.stderr or proc.stdout or "").strip()
        if attempt < attempts and (
            "gateway closed" in last_detail
            or "handshake" in last_detail
            or "Gateway target:" in last_detail
        ):
            time.sleep(min(2 * attempt, 8))
            continue
        break
    raise RuntimeError(f"openclaw infer failed after {attempts} attempt(s): {last_detail[-800:]}")


def chat_with_model(
    model_id: str,
    *,
    ollama_host: str,
    openai_base_url: str,
    openai_api_key: str,
    codex_base_url: str = "",
    codex_api_key: str = "",
    system: str,
    user: str,
    timeout: int,
) -> str:
    if is_openclaw_codex_model(model_id):
        if codex_base_url:
            if not codex_api_key:
                raise RuntimeError(
                    f"missing NEWS_CODEX_API_KEY for Codex HTTP endpoint {codex_base_url}; "
                    "refusing to fall back to the busy local gateway"
                )
            return openai_chat(
                codex_base_url,
                codex_api_key,
                provider_api_model_name(model_id),
                system,
                user,
                timeout,
            )
        return openclaw_model_chat(model_id, system, user, timeout)
    if is_openai_model(model_id):
        if not openai_api_key:
            raise RuntimeError(f"missing OPENAI_API_KEY for {model_id}")
        return openai_chat(
            openai_base_url,
            openai_api_key,
            provider_api_model_name(model_id),
            system,
            user,
            timeout,
        )
    return ollama_chat(ollama_host, ollama_api_model_name(model_id), system, user, timeout)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


def canonical_source_url(url: str) -> str:
    """URL 级去重键：同一来源地址只处理一次，忽略 fragment 和无意义尾斜杠。"""
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        p = urllib.parse.urlsplit(raw)
    except Exception:
        return raw.rstrip("/")
    scheme = (p.scheme or "https").lower()
    host = (p.netloc or "").lower()
    path = p.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit((scheme, host, path, p.query, ""))


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


def load_published_items(path: Path) -> dict[str, Any]:
    try:
        data = load_json(path)
    except Exception:
        return {"version": 1, "items": []}
    return {"version": 1, "items": list(data.get("items", []))}


def append_recent_items(path: Path, data: dict[str, Any], articles: list[dict], now_ts: int) -> None:
    items = list(data.get("items", []))
    seen = {str(item.get("fingerprint") or "") for item in items}
    seen_urls = {canonical_source_url(str(item.get("url") or "")) for item in items}
    for art in articles:
        fp = str(art.get("fingerprint") or "")
        url_key = canonical_source_url(str(art.get("url") or ""))
        if (fp and fp in seen) or (url_key and url_key in seen_urls):
            continue
        if fp:
            seen.add(fp)
        if url_key:
            seen_urls.add(url_key)
        items.append(
            {
                "fingerprint": fp,
                "title": art.get("title", ""),
                "url": art.get("url", ""),
                "url_key": url_key,
                "published_ts": int(art.get("published_ts") or 0),
                "seen_ts": now_ts,
            }
        )
    save_json(path, {"version": 1, "items": items})


def append_published_items(
    path: Path,
    data: dict[str, Any],
    selected_sections: dict[str, list[dict[str, Any]]],
    *,
    job_name: str,
    window_start_ts: int,
    window_end_ts: int,
    now_ts: int,
) -> None:
    """只在正式发布成功后调用；测试运行不应消耗发布状态。"""
    items = list(data.get("items", []))
    seen_urls = {canonical_source_url(str(item.get("url") or item.get("url_key") or "")) for item in items}
    for section, selected in selected_sections.items():
        for item in selected:
            url_key = canonical_source_url(str(item.get("source_url") or ""))
            if not url_key or url_key in seen_urls:
                continue
            seen_urls.add(url_key)
            items.append(
                {
                    "url": item.get("source_url", ""),
                    "url_key": url_key,
                    "title": item.get("source_title", ""),
                    "summary_zh": item.get("summary_zh", ""),
                    "section": section,
                    "category": item.get("category", "other"),
                    "published_ts": int(item.get("published_ts") or 0),
                    "broadcast_job": job_name,
                    "broadcast_window_start_ts": window_start_ts,
                    "broadcast_window_end_ts": window_end_ts,
                    "broadcasted_ts": now_ts,
                    "status": "broadcasted",
                }
            )
    save_json(path, {"version": 1, "items": items})


def reset_published_items_for_window(path: Path, window_start_ts: int, window_end_ts: int) -> int:
    data = load_published_items(path)
    kept = []
    removed = 0
    for item in data.get("items", []):
        start = int(item.get("broadcast_window_start_ts") or 0)
        end = int(item.get("broadcast_window_end_ts") or 0)
        overlaps = start < window_end_ts and end > window_start_ts
        if overlaps:
            removed += 1
        else:
            kept.append(item)
    save_json(path, {"version": 1, "items": kept})
    return removed


def mark_published_run_dir(run_dir: Path, state_path: Path = PUBLISHED_ITEMS_PATH) -> int:
    meta = load_json(run_dir / "meta.json")
    selected = load_json(run_dir / "selected_items.json")
    before = load_published_items(state_path)
    before_count = len(before.get("items", []))
    append_published_items(
        state_path,
        before,
        selected.get("sections", {}),
        job_name=str(meta.get("job") or ""),
        window_start_ts=int(meta.get("window_start_ts") or 0),
        window_end_ts=int(meta.get("window_end_ts") or 0),
        now_ts=int(time.time()),
    )
    after_count = len(load_published_items(state_path).get("items", []))
    return after_count - before_count


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


def check_processor_health(
    model: str,
    *,
    ollama_host: str,
    openai_base_url: str,
    openai_api_key: str,
    codex_base_url: str = "",
    codex_api_key: str = "",
    timeout: int,
) -> tuple[bool, str]:
    try:
        health_timeout = min(max(timeout, 1), 240 if is_openclaw_codex_model(model) else 20)
        result = chat_with_model(
            model,
            ollama_host=ollama_host,
            openai_base_url=openai_base_url,
            openai_api_key=openai_api_key,
            codex_base_url=codex_base_url,
            codex_api_key=codex_api_key,
            system="只输出 JSON，不要解释。",
            user='输出 {"ok":true}',
            timeout=health_timeout,
        )
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    if not result:
        return False, "empty response"
    return True, "ok"


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
    "准确性优先于流畅性；只改写原文已有事实，不得补充背景知识或推断。\n"
    "【输出格式（严格两行）】\n"
    "• 一句话中文摘要（20-60字，概括核心事实）\n"
    "链接：{url}\n\n"
    "【规则】\n"
    "• 以「• 」（U+2022 圆点+空格）开头\n"
    "• 只输出摘要和链接，不要解释、不要前言后语\n"
    "• 公司隶属、人物身份、数字、地点、因果关系必须能在标题或正文中找到；没有把握就省略\n"
    "• 不要写“旗下、母公司、关联公司、导致、确认”等原文没有明确给出的关系词\n"
    "• 如果原文内容无实质新闻价值，输出空文本"
)


def summarize_article_prompt(title: str, url: str, content: str, max_chars: int = 1500) -> tuple[str, str]:
    """为单篇文章生成 Qwen 调用的 system/user prompt。"""
    sys_p = SUMMARIZE_SYSTEM_PROMPT.replace("{url}", url)
    body = content[:max_chars] if len(content) > max_chars else content
    user_p = f"标题：{title}\n链接：{url}\n\n正文：\n{body}"
    return sys_p, user_p


ENGLISH_TERM_MAP = {
    "Asia-Pacific markets set for weaker open as oil climbs on Iran tensions, Fed holds rates": "亚太市场或因伊朗紧张局势推高油价而低开，美联储维持利率不变",
    "South Korean court hikes ex-president's sentence for obstructing justice": "韩国法院因妨碍司法加重前总统刑期",
    "Two dead after small plane crashes into Australia airport hangar": "澳大利亚一架小型飞机撞入机场机库，造成两人死亡",
    "Afghanistan women can return to competition": "阿富汗女足运动员获准重返比赛",
    "Fed holds rates steady but with highest level of dissent since 1992": "美联储维持利率不变，但异议程度创1992年以来最高",
}

TERM_TRANSLATIONS = {
    "Asia-Pacific": "亚太",
    "markets": "市场",
    "market": "市场",
    "oil": "石油",
    "Iran": "伊朗",
    "Fed": "美联储",
    "rates": "利率",
    "Trump": "特朗普",
    "Russia": "俄罗斯",
    "Ukraine": "乌克兰",
    "China": "中国",
    "Chinese": "中国",
    "Japan": "日本",
    "Japanese": "日本",
    "South Korean": "韩国",
    "court": "法院",
    "sentence": "刑期",
    "president": "总统",
    "plane": "飞机",
    "crashes": "坠毁",
    "Australia": "澳大利亚",
    "airport": "机场",
    "women": "女性",
    "competition": "比赛",
    "OpenAI": "OpenAI",
    "Microsoft": "微软",
    "Amazon": "亚马逊",
    "Meta": "Meta",
    "Alphabet": "Alphabet",
    "stock": "股价",
    "earnings": "财报",
    "CEO": "CEO",
}

def looks_mostly_chinese(text: str) -> bool:
    chars = [ch for ch in text if ch.isalpha() or "\u4e00" <= ch <= "\u9fff"]
    if not chars:
        return True
    cjk = sum(1 for ch in chars if "\u4e00" <= ch <= "\u9fff")
    return cjk / len(chars) >= 0.35


def deterministic_chinese_fallback(title: str) -> str:
    """模型失败时只能使用可信中文映射；不能把外文标题包装后发布。"""
    title_clean = " ".join((title or "").split()).strip()
    if title_clean in ENGLISH_TERM_MAP:
        return ENGLISH_TERM_MAP[title_clean]
    if len(title_clean) > 120:
        title_clean = title_clean[:117] + "..."
    if not title_clean:
        return ""
    if re.search(r"[\u3040-\u30ff]", title_clean):
        return ""
    if looks_mostly_chinese(title_clean):
        return title_clean
    return ""


def deterministic_summary_from_article(title: str, url: str) -> str:
    """模型摘要失败时的最小中文兜底（保留来源链接）。"""
    fallback = deterministic_chinese_fallback(title)
    if not fallback:
        return ""
    return f"• {fallback}\n链接：{url}"


ARTICLE_PROCESS_SYSTEM_PROMPT = (
    "你是新闻条目处理器。只根据输入的单篇原始稿件生成结构化 JSON，不要输出 Markdown 或解释。\n"
    "summary_zh 必须是中文一句话，20-60 字，准确概括核心事实；不得补充原文没有的信息。\n"
    "region 只能是 japan、china、us、europe、ai、technology、entertainment、world、markets；"
    "category 用 politics、economy、society、technology、culture、entertainment、sports、health、environment、risk、other 之一。"
)


def _safe_item_id(index: int, source_url: str, fingerprint: str = "") -> str:
    base = canonical_source_url(source_url) or fingerprint or str(index)
    return f"{index:03d}_{hashlib.sha1(base.encode('utf-8')).hexdigest()[:12]}"


def archive_raw_article_items(run_dir: Path, all_articles: dict[str, list[dict]]) -> list[dict[str, Any]]:
    raw_dir = run_dir / "raw_items"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_items: list[dict[str, Any]] = []
    index = 1
    for batch_id, articles in all_articles.items():
        for art in articles:
            item_id = _safe_item_id(index, str(art.get("url") or ""), str(art.get("fingerprint") or ""))
            item = {
                "version": 1,
                "item_id": item_id,
                "original_batch": batch_id,
                "title": art.get("title", ""),
                "source_url": art.get("url", ""),
                "source_url_key": canonical_source_url(str(art.get("url") or "")),
                "source_feed": art.get("source_feed", ""),
                "published_at": art.get("published_at", ""),
                "published_ts": int(art.get("published_ts") or 0),
                "fingerprint": art.get("fingerprint", ""),
                "snippet": art.get("snippet", ""),
                "raw_content": art.get("content", ""),
                "fetch_ok": bool(art.get("fetch_ok")),
                "fetch_error": art.get("fetch_error", ""),
            }
            save_json(raw_dir / f"{item_id}.json", item)
            raw_items.append(item)
            index += 1
    save_json(run_dir / "raw_items_index.json", {"version": 1, "items": raw_items})
    return raw_items


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = strip_think_blocks(text).strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if m:
        cleaned = m.group(0)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("model did not return a JSON object")
    return data


def process_raw_article_item(
    item: dict[str, Any],
    *,
    ollama_host: str,
    openai_base_url: str,
    openai_api_key: str,
    codex_base_url: str = "",
    codex_api_key: str = "",
    model: str,
    fallback_model: str,
    timeout: int,
    max_input_chars: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "version": 1,
        "item_id": item.get("item_id", ""),
        "source_url": item.get("source_url", ""),
        "source_url_key": item.get("source_url_key", ""),
        "source_title": item.get("title", ""),
        "source_feed": item.get("source_feed", ""),
        "published_at": item.get("published_at", ""),
        "published_ts": int(item.get("published_ts") or 0),
        "original_batch": item.get("original_batch", "world"),
        "region": item.get("original_batch", "world"),
        "category": "other",
        "summary_zh": "",
        "included": False,
        "skip_reason": "",
        "processor": model,
    }
    if not item.get("fetch_ok") or not item.get("raw_content"):
        result["skip_reason"] = "fetch_failed_or_empty"
        return result

    body = str(item.get("raw_content") or "")[:max_input_chars]
    user = json.dumps(
        {
            "title": item.get("title", ""),
            "url": item.get("source_url", ""),
            "published_at": item.get("published_at", ""),
            "original_batch": item.get("original_batch", "world"),
            "content": body,
            "output_schema": {
                "summary_zh": "中文一句话新闻主题",
                "region": "japan|china|us|europe|ai|technology|entertainment|world|markets",
                "category": "politics|economy|society|technology|culture|entertainment|sports|health|environment|risk|other",
            },
        },
        ensure_ascii=False,
    )
    used_model = model
    try:
        raw_response = chat_with_model(
            model,
            ollama_host=ollama_host,
            openai_base_url=openai_base_url,
            openai_api_key=openai_api_key,
            codex_base_url=codex_base_url,
            codex_api_key=codex_api_key,
            system=ARTICLE_PROCESS_SYSTEM_PROMPT,
            user=user,
            timeout=timeout,
        )
        parsed = _parse_json_object(raw_response)
        summary = str(parsed.get("summary_zh") or "").strip()
        region = str(parsed.get("region") or result["region"]).strip().lower()
        category = str(parsed.get("category") or "other").strip().lower()
    except Exception as e:
        print(f"[pipeline] process item {item.get('item_id')} primary {model} failed: {e}", file=sys.stderr)
        if fallback_model and fallback_model != model:
            try:
                used_model = fallback_model
                raw_response = chat_with_model(
                    fallback_model,
                    ollama_host=ollama_host,
                    openai_base_url=openai_base_url,
                    openai_api_key=openai_api_key,
                    codex_base_url=codex_base_url,
                    codex_api_key=codex_api_key,
                    system=ARTICLE_PROCESS_SYSTEM_PROMPT,
                    user=user,
                    timeout=timeout,
                )
                parsed = _parse_json_object(raw_response)
                summary = str(parsed.get("summary_zh") or "").strip()
                region = str(parsed.get("region") or result["region"]).strip().lower()
                category = str(parsed.get("category") or "other").strip().lower()
            except Exception as e2:
                print(f"[pipeline] process item {item.get('item_id')} fallback {fallback_model} failed: {e2}", file=sys.stderr)
                summary = ""
                region = result["region"]
                category = "other"
                result["skip_reason"] = "model_failed"
        else:
            summary = ""
            region = result["region"]
            category = "other"
            result["skip_reason"] = "model_failed"

    allowed_regions = set(DEFAULT_NEWS_REGIONS)
    allowed_categories = {
        "politics",
        "economy",
        "society",
        "technology",
        "culture",
        "entertainment",
        "sports",
        "health",
        "environment",
        "risk",
        "other",
    }
    if region not in allowed_regions:
        region = result["region"] if result["region"] in allowed_regions else "world"
    if category not in allowed_categories:
        category = "other"
    result["region"] = region
    result["category"] = category
    result["summary_zh"] = summary
    result["processor"] = used_model
    if not summary:
        result["skip_reason"] = result["skip_reason"] or "no_chinese_summary"
    elif re.search(r"[\u3040-\u30ff]", summary) or not looks_mostly_chinese(summary):
        result["summary_zh"] = ""
        result["skip_reason"] = "non_chinese_summary"
    else:
        result["included"] = True
        result["skip_reason"] = ""
    return result


def process_raw_article_items(
    run_dir: Path,
    raw_items: list[dict[str, Any]],
    *,
    ollama_host: str,
    openai_base_url: str,
    openai_api_key: str,
    codex_base_url: str = "",
    codex_api_key: str = "",
    model: str,
    fallback_model: str,
    timeout: int,
    max_input_chars: int,
) -> list[dict[str, Any]]:
    processed_dir = run_dir / "processed_items"
    processed_dir.mkdir(parents=True, exist_ok=True)
    processed: list[dict[str, Any]] = []
    for item in raw_items:
        result = process_raw_article_item(
            item,
            ollama_host=ollama_host,
            openai_base_url=openai_base_url,
            openai_api_key=openai_api_key,
            codex_base_url=codex_base_url,
            codex_api_key=codex_api_key,
            model=model,
            fallback_model=fallback_model,
            timeout=timeout,
            max_input_chars=max_input_chars,
        )
        save_json(processed_dir / f"{result['item_id']}.json", result)
        processed.append(result)
    save_json(run_dir / "processed_items_index.json", {"version": 1, "items": processed})
    return processed


def write_selected_items_and_workers(
    run_dir: Path,
    plan: dict,
    processed_items: list[dict[str, Any]],
    fallback_line: str,
) -> dict[str, list[dict[str, Any]]]:
    selected: dict[str, list[dict[str, Any]]] = {b["id"]: [] for b in plan["batches"]}
    sticky_batches = {"japan", "china", "us", "europe"}
    def normalize_content_section(region: str, category: str) -> str:
        if region == "ai":
            if category == "technology":
                return "ai"
            return "technology"
        if region == "technology" and category != "technology":
            if category in {"economy", "risk"}:
                return "markets"
            if category in {"entertainment", "culture", "sports"}:
                return "entertainment"
            return "world"
        if region == "entertainment" and category not in {"entertainment", "culture", "sports"}:
            if category == "technology":
                return "technology"
            if category in {"economy", "risk"}:
                return "markets"
            return "world"
        return region

    for item in processed_items:
        if not item.get("included"):
            continue
        original_batch = str(item.get("original_batch") or "")
        region = str(item.get("region") or "world")
        category = str(item.get("category") or "other")
        if original_batch in sticky_batches and original_batch in selected:
            # Region classification has priority over content classification.
            region = original_batch
        else:
            region = normalize_content_section(region, category)
        if region not in selected:
            region = "world"
        selected[region].append(item)

    for items in selected.values():
        items.sort(key=lambda x: int(x.get("published_ts") or 0), reverse=True)

    save_json(run_dir / "selected_items.json", {"version": 1, "sections": selected})
    for b in plan["batches"]:
        bid = b["id"]
        lines: list[str] = []
        for item in selected.get(bid, []):
            lines.append(f"• {item['summary_zh']}")
            if plan.get("_format_rules", {}).get("includeLinksInBroadcast", False) and item.get("source_url"):
                lines.append(f"链接：{item['source_url']}")
        if not lines and not plan.get("_format_rules", {}).get("omitEmptySections", False):
            lines.append(f"• {fallback_line}")
        (run_dir / f"worker_{bid}.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return selected


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
            fallback = deterministic_summary_from_article(art["title"], art["url"])
            if fallback:
                fragments.append(fallback)
            continue
        cleaned = strip_think_blocks(result)
        if cleaned and not cleaned.startswith("[") and len(cleaned) > 10:
            fragments.append(cleaned)
        else:
            fallback = deterministic_summary_from_article(art["title"], art["url"])
            if fallback:
                fragments.append(fallback)

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
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(sec)
        if not plan.get("_format_rules", {}).get("omitEmptySections", False):
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
        f"从第 3 行开始，必须按顺序且仅出现以下 {len(fr['outline'])} 个编号小节：\n"
        f"{outline}\n"
        "全文只允许上面这些小节标题行使用数字编号；其他任何地方不得出现数字编号。\n"
        "【禁止的编号形式举例】1. xxx / 2. xxx / 1、xxx / (1) xxx / ① xxx\n"
        "以上在条目行内全部禁止。\n"
        "一级标题必须加粗（用 ** 包裹），如 **1. 日本**。\n"
        "每个分区标题前必须保留一个空行，让标题和上一分区内容分开。\n"
        "每个小节内条目一律用「• 」（Unicode 圆点 U+2022 + 空格）开头。\n"
        "不要使用短横线 - 作为条目符号（Discord 会错误渲染）。\n"
        "若某节工人未提供合格条目，直接隐藏该小节；不要输出无新闻占位句。\n"
        "公开播报稿禁止输出 URL、链接行、Markdown 链接或裸域名；来源 URL 只保留在后台 JSON 记录。\n\n"
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
    omit_empty = bool(fr.get("omitEmptySections", False))

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
        bid = batch_ids[i] if i < len(batch_ids) else None
        items = batch_content.get(bid, []) if bid else []
        if items:
            if result_lines and result_lines[-1] != "":
                result_lines.append("")
            result_lines.append(sec_title)
            result_lines.extend(items)
        elif not omit_empty:
            if result_lines and result_lines[-1] != "":
                result_lines.append("")
            result_lines.append(sec_title)
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

        if content and not content.startswith("•") and not content.startswith(bullet):
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(header)
            for cline in content.splitlines():
                cline = cline.strip()
                if cline:
                    lines.append(cline)
        elif content:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(header)
            lines.append(content)
        elif not fr.get("omitEmptySections", False):
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(header)
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
    parser.add_argument("--ignore-recent", action="store_true", help="手动验收用：忽略跨运行去重状态")
    parser.add_argument(
        "--no-record-recent",
        action="store_true",
        help="手动验收用：不把本次文章写入跨运行去重状态",
    )
    parser.add_argument(
        "--broadcast-mode",
        choices=("official", "test"),
        default="official",
        help="official 才会写入已播报状态；test 不消耗正式播报状态",
    )
    parser.add_argument("--reset-published-window-start", type=int, help="重置已播报状态的窗口起点 Unix 秒")
    parser.add_argument("--reset-published-window-end", type=int, help="重置已播报状态的窗口终点 Unix 秒")
    parser.add_argument("--mark-published-run-dir", type=Path, help="Discord 成功发送后，将指定 run-dir 的 selected_items 标记为已正式播报")
    parser.add_argument("--openai-timeout", type=int, default=300)
    parser.add_argument("--ollama-timeout", type=int, default=300)
    args = parser.parse_args()

    if args.mark_published_run_dir:
        added = mark_published_run_dir(args.mark_published_run_dir.resolve())
        print(f"MARK_PUBLISHED_OK added={added}")
        return 0

    if args.reset_published_window_start is not None or args.reset_published_window_end is not None:
        if args.reset_published_window_start is None or args.reset_published_window_end is None:
            raise SystemExit("--reset-published-window-start and --reset-published-window-end must be used together")
        if args.reset_published_window_start >= args.reset_published_window_end:
            raise SystemExit("reset window start must be before end")
        removed = reset_published_items_for_window(
            PUBLISHED_ITEMS_PATH,
            args.reset_published_window_start,
            args.reset_published_window_end,
        )
        print(f"RESET_PUBLISHED_OK removed={removed}")
        return 0

    load_runtime_env_files()
    cfg = load_json(args.config)
    job = job_spec(cfg, args.job)
    model_cfg = cfg.get("model", {})

    worker_model_raw = os.environ.get(
        "NEWS_WORKER_MODEL",
        model_cfg.get("newsWorker", "openai-codex/gpt-5.5"),
    )
    fallback_model_raw = os.environ.get(
        "NEWS_FALLBACK_MODEL",
        model_cfg.get("chatFallback", "ollama/qwen3:14b"),
    )
    finalize_model_raw = model_cfg.get("newsFinalize", "openai-codex/gpt-5.5")
    orch_model = os.environ.get(
        "NEWS_ORCHESTRATOR_MODEL",
        model_cfg.get("newsOrchestrator", "openai-codex/gpt-5.5"),
    )

    ollama_worker_model = ollama_api_model_name(worker_model_raw)
    ollama_finalize_model = ollama_api_model_name(finalize_model_raw)
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get("NEWS_OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    codex_base_url = resolve_codex_base_url(cfg)
    codex_api_key = resolve_codex_api_key(cfg)
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
            "fallback_model": fallback_model_raw,
            "finalize_model": finalize_model_raw,
            "orchestrator_model": orch_model,
            "worker_call_mode": "per-article",
            "ollama_api_worker": ollama_worker_model,
            "ollama_api_finalize": ollama_finalize_model,
            "ollama_base_url": ollama_host,
            "codex_base_url": codex_base_url,
            "codex_http_enabled": bool(codex_base_url),
            "codex_api_key_present": bool(codex_api_key),
            "window_start_ts": window_start_ts,
            "window_end_ts": window_end_ts,
            "cross_run_dedupe_hours": dedupe_hours,
            "require_timestamp_in_window": require_timestamp,
            "ignore_recent": args.ignore_recent,
            "record_recent": not args.no_record_recent,
            "broadcast_mode": args.broadcast_mode,
            "record_published_after_delivery": args.broadcast_mode == "official" and not args.no_record_recent,
        },
    )

    fallback_text_tpl = plan["fallback_no_news"]

    # --- discover + fetch ---
    fetcher = _load_fetcher()
    trace.step("load-fetcher", "ok", detail="news_fetcher loaded", tool="python")
    all_articles: dict[str, list] = {}
    NEWS_STATE_DIR.mkdir(parents=True, exist_ok=True)
    recent_items = (
        {"version": 1, "items": []}
        if args.ignore_recent
        else load_recent_items(RECENT_ITEMS_PATH, ts, dedupe_hours)
    )
    published_items = load_published_items(PUBLISHED_ITEMS_PATH)
    seen_fingerprints = {
        str(item.get("fingerprint") or "")
        for item in recent_items.get("items", [])
        if str(item.get("fingerprint") or "")
    }
    seen_source_urls = {
        canonical_source_url(str(item.get("url") or item.get("url_key") or ""))
        for item in recent_items.get("items", [])
        if canonical_source_url(str(item.get("url") or item.get("url_key") or ""))
    }
    published_source_urls = {
        canonical_source_url(str(item.get("url") or item.get("url_key") or ""))
        for item in published_items.get("items", [])
        if canonical_source_url(str(item.get("url") or item.get("url_key") or ""))
    }

    for b in plan["batches"]:
        bid = b["id"]
        if args.skip_discover or args.dry_run:
            all_articles[bid] = []
            trace.step("discover", "skipped", detail=bid, tool="rss")
            continue
        source_policy = cfg.get("sourcePolicy", {}) or {}
        configured_feeds = (source_policy.get("rssFeedsByBatch", {}) or {}).get(bid)
        if configured_feeds and isinstance(configured_feeds, list):
            feed_list = [str(x).strip() for x in configured_feeds if str(x).strip()]
        else:
            feed_list = None
        priority_keywords = source_policy.get("priorityKeywords", []) or []
        max_per_batch = int(source_policy.get("maxArticlesPerBatch", 8) or 8)
        print(f"[pipeline] discover {bid}...", file=sys.stderr)
        trace.step("discover", "running", detail=bid, tool="rss")
        articles = fetcher.discover_articles(
            bid,
            feeds=feed_list,
            max_per_batch=max_per_batch,
            window_start_ts=window_start_ts,
            window_end_ts=window_end_ts,
            exclude_fingerprints=seen_fingerprints,
            require_timestamp=require_timestamp,
            priority_keywords=priority_keywords,
        )
        if not args.skip_fetch:
            print(f"[pipeline] fetch {bid}: {len(articles)} articles...", file=sys.stderr)
            trace.step("fetch", "running", detail=f"{bid}: {len(articles)} articles", tool="http")
            fetcher.fetch_and_fill(articles, max_chars=max_worker_chars)
        deduped_articles = []
        skipped_by_url = 0
        for a in articles:
            url_key = canonical_source_url(a.url)
            if url_key and (url_key in seen_source_urls or url_key in published_source_urls):
                skipped_by_url += 1
                continue
            if url_key:
                seen_source_urls.add(url_key)
            deduped_articles.append(
                {
                "title": a.title,
                "url": a.url,
                "content": a.content,
                "fetch_ok": a.fetch_ok,
                "snippet": a.snippet,
                "published_at": a.published_at,
                "published_ts": a.published_ts,
                "fingerprint": a.fingerprint,
                "source_feed": a.source_feed,
                }
            )
        all_articles[bid] = deduped_articles
        for art in all_articles[bid]:
            fp = str(art.get("fingerprint") or "")
            if fp:
                seen_fingerprints.add(fp)
        save_json(run_dir / f"articles_{bid}.json", all_articles[bid])
        trace.step(
            "discover-fetch",
            "ok",
            detail=f"{bid}: discovered {len(articles)} articles, url_dupes={skipped_by_url}, fetched {len([a for a in all_articles[bid] if a.get('fetch_ok')])}",
            tool="rss+http",
        )

    # --- per-article classification ---
    # 每条新闻单独归类到配置的地区/主题栏，避免整批搬家或为凑数把不相关新闻留在区域栏。
    source_policy = cfg.get("sourcePolicy", {}) or {}
    region_kw_map = source_policy.get("regionKeywordsByBatch", {}) or {}
    market_keywords = source_policy.get("marketKeywords", []) or []
    batch_ids = [b["id"] for b in plan["batches"]]
    classified: dict[str, list[dict]] = {bid: [] for bid in batch_ids}
    seen_classified: set[str] = set()
    moved = 0
    for original_batch, articles in list(all_articles.items()):
        for art in articles:
            target = fetcher.classify_article_batch(
                original_batch,
                art.get("title", ""),
                art.get("url", ""),
                art.get("snippet", ""),
                region_kw_map,
                market_keywords,
            )
            if target not in classified:
                target = "world"
            fp = str(art.get("fingerprint") or art.get("url") or "")
            if fp and fp in seen_classified:
                continue
            if fp:
                seen_classified.add(fp)
            classified[target].append(art)
            if target != original_batch:
                moved += 1
    all_articles = classified
    for bid, articles in all_articles.items():
        save_json(run_dir / f"articles_{bid}.json", articles)
    if moved:
        trace.step("classify", "ok", detail=f"moved={moved}", tool="article-classifier")

    # --- archive raw items + process each article into structured Chinese records ---
    raw_items = archive_raw_article_items(run_dir, all_articles)
    trace.step("archive-raw", "ok", detail=f"raw_items={len(raw_items)}", tool="filesystem")

    if args.skip_worker:
        processed_items = [
            {
                "version": 1,
                "item_id": item.get("item_id", ""),
                "source_url": item.get("source_url", ""),
                "source_title": item.get("title", ""),
                "region": item.get("original_batch", "world"),
                "category": "other",
                "summary_zh": "",
                "included": False,
                "skip_reason": "skip-worker",
            }
            for item in raw_items
        ]
        save_json(run_dir / "processed_items_index.json", {"version": 1, "items": processed_items})
        trace.step("process-items", "skipped", detail=f"items={len(raw_items)}", tool="ollama")
    elif args.dry_run:
        processed_items = [
            {
                "version": 1,
                "item_id": f"dry_{b['id']}",
                "source_url": "https://example.com",
                "source_title": b["outline_line"],
                "region": b["id"],
                "category": "other",
                "summary_zh": f"干跑占位：{b['outline_line']}暂无真实采集条目",
                "included": True,
                "skip_reason": "",
            }
            for b in plan["batches"]
        ]
        save_json(run_dir / "processed_items_index.json", {"version": 1, "items": processed_items})
        trace.step("process-items", "skipped", detail="dry-run placeholders", tool="ollama")
    else:
        trace.step("process-items", "running", detail=f"items={len(raw_items)}", tool=worker_model_raw)
        fetched_raw = len([x for x in raw_items if x.get("fetch_ok")])
        if fetched_raw > 0:
            healthy, health_detail = check_processor_health(
                worker_model_raw,
                ollama_host=ollama_host,
                openai_base_url=base_url,
                openai_api_key=api_key,
                codex_base_url=codex_base_url,
                codex_api_key=codex_api_key,
                timeout=args.openai_timeout if is_openai_model(worker_model_raw) else args.ollama_timeout,
            )
            if not healthy and fallback_model_raw and fallback_model_raw != worker_model_raw:
                fallback_healthy, fallback_detail = check_processor_health(
                    fallback_model_raw,
                    ollama_host=ollama_host,
                    openai_base_url=base_url,
                    openai_api_key=api_key,
                    codex_base_url=codex_base_url,
                    codex_api_key=codex_api_key,
                    timeout=args.openai_timeout if is_openai_model(fallback_model_raw) else args.ollama_timeout,
                )
                if fallback_healthy:
                    healthy = True
                    health_detail = f"primary_failed={health_detail}; fallback_ok={fallback_model_raw}"
                else:
                    health_detail = f"primary_failed={health_detail}; fallback_failed={fallback_detail}"
            if not healthy:
                save_json(
                    run_dir / "processor_failure.json",
                    {
                        "error": "processor_healthcheck_failed",
                        "message": "Fetched real articles, but the Chinese processing model is unavailable; refusing to publish.",
                        "fetched_raw": fetched_raw,
                        "processed": 0,
                        "skip_reasons": {"processor_healthcheck_failed": fetched_raw},
                        "worker_model": worker_model_raw,
                        "fallback_model": fallback_model_raw,
                        "ollama_base_url": ollama_host,
                        "codex_base_url": codex_base_url,
                        "codex_http_enabled": bool(codex_base_url),
                        "codex_api_key_present": bool(codex_api_key),
                        "health_detail": health_detail,
                    },
                )
                trace.step("process-items", "failed", detail=f"healthcheck failed: {health_detail}", tool=worker_model_raw)
                trace.finish("failed", "processor-unavailable", final_message=str(run_dir / "processor_failure.json"))
                print(
                    "PIPELINE_FAIL processor_unavailable "
                    f"fetched={fetched_raw} processed=0 health={health_detail!r} run_dir={run_dir}",
                    file=sys.stderr,
                )
                return 4
        processed_items = process_raw_article_items(
            run_dir,
            raw_items,
            ollama_host=ollama_host,
            openai_base_url=base_url,
            openai_api_key=api_key,
            codex_base_url=codex_base_url,
            codex_api_key=codex_api_key,
            model=worker_model_raw,
            fallback_model=fallback_model_raw,
            timeout=args.openai_timeout if is_openai_model(worker_model_raw) else args.ollama_timeout,
            max_input_chars=max_worker_chars,
        )
        included = len([x for x in processed_items if x.get("included")])
        trace.step("process-items", "ok", detail=f"included={included}/{len(processed_items)}", tool=worker_model_raw)
        if fetched_raw > 0 and included == 0:
            reasons: dict[str, int] = {}
            for item in processed_items:
                key = str(item.get("skip_reason") or "unknown")
                reasons[key] = reasons.get(key, 0) + 1
            save_json(
                run_dir / "processor_failure.json",
                {
                    "error": "no_processed_news_items",
                    "message": "Fetched real articles, but none passed Chinese processing; refusing to publish an empty official broadcast.",
                    "fetched_raw": fetched_raw,
                    "processed": len(processed_items),
                    "skip_reasons": reasons,
                    "worker_model": worker_model_raw,
                    "fallback_model": fallback_model_raw,
                    "ollama_base_url": ollama_host,
                },
            )
            trace.step("process-items", "failed", detail=f"fetched={fetched_raw}, included=0, reasons={reasons}", tool=worker_model_raw)
            trace.finish("failed", "processor-unavailable", final_message=str(run_dir / "processor_failure.json"))
            print(
                "PIPELINE_FAIL processor_unavailable "
                f"fetched={fetched_raw} processed={len(processed_items)} reasons={reasons} run_dir={run_dir}",
                file=sys.stderr,
            )
            return 4

    selected = write_selected_items_and_workers(run_dir, plan, processed_items, fallback_text_tpl)
    trace.step(
        "select-final",
        "ok",
        detail=", ".join(f"{k}={len(v)}" for k, v in selected.items()),
        tool="selector",
    )

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
    # 不通过才走 Codex 主模型 → Qwen/Ollama 兜底 → mechanical fallback。
    if verify_text_fn:
        ok_draft, draft_errors = verify_text_fn(draft, cfg)
        if ok_draft:
            print("[pipeline] merged draft passes verify directly, skipping finalize model", file=sys.stderr)
            final_path.write_text(draft, encoding="utf-8")
            trace.step("verify", "ok", detail="merged draft passed verify directly", tool="verify")
            if not args.no_record_recent:
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
        trace.step("finalize", "running", detail=f"attempt {attempt}", tool=finalize_model_raw)
        fin_sys = finalize_system_prompt(cfg, plan, last_errors if attempt > 1 else None)
        fin_user = "以下是已格式化的合并草稿，只需微调格式即可输出最终成稿（不要改写内容或链接）：\n\n" + draft

        try:
            print(f"[pipeline] finalize attempt {attempt}: primary ({finalize_model_raw})...", file=sys.stderr)
            final_text = chat_with_model(
                finalize_model_raw,
                ollama_host=ollama_host,
                openai_base_url=base_url,
                openai_api_key=api_key,
                codex_base_url=codex_base_url,
                codex_api_key=codex_api_key,
                system=fin_sys,
                user=fin_user,
                timeout=args.openai_timeout * 2 if is_openai_model(finalize_model_raw) else args.ollama_timeout,
            )
        except Exception as e:
            print(f"[pipeline] primary finalize failed: {e}", file=sys.stderr)
            if fallback_model_raw and fallback_model_raw != finalize_model_raw:
                print(f"[pipeline] fallback finalize to {fallback_model_raw}...", file=sys.stderr)
                try:
                    final_text = chat_with_model(
                        fallback_model_raw,
                        ollama_host=ollama_host,
                        openai_base_url=base_url,
                        openai_api_key=api_key,
                        codex_base_url=codex_base_url,
                        codex_api_key=codex_api_key,
                        system=fin_sys,
                        user=fin_user,
                        timeout=args.openai_timeout * 2 if is_openai_model(fallback_model_raw) else args.ollama_timeout,
                    )
                except Exception as e2:
                    print(f"[pipeline] fallback finalize also failed: {e2}", file=sys.stderr)
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

    if not args.no_record_recent:
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
