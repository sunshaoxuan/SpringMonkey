#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from harness_intent_agent import call_model, load_runtime_env_files


WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
USER_AGENT = "OpenClaw-WebResearch/1.0 (+https://github.com/sunshaoxuan/SpringMonkey)"
URL_RE = re.compile(r"https?://[^\s<>()\]\"']+", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"<(script|style)[\s\S]*?</\1>", re.IGNORECASE)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""


@dataclass
class FetchResult:
    url: str
    ok: bool
    status: int | None = None
    title: str = ""
    text: str = ""
    error: str = ""


@dataclass
class ResearchEvidence:
    query: str
    provider: str
    search_attempted: bool = False
    fetch_attempted: bool = False
    browser_attempted: bool = False
    search_error: str = ""
    browser_error: str = ""
    candidates: list[dict[str, Any]] = field(default_factory=list)
    fetches: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, str]] = field(default_factory=list)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def invocation_log_path() -> Path:
    configured = os.environ.get("OPENCLAW_HARNESS_WEB_RESEARCH_LOG", "").strip()
    return Path(configured) if configured else WORKSPACE / "var" / "harness_web_research_invocations.jsonl"


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def read_secret_env(*names: str) -> str:
    load_runtime_env_files()
    for name in names:
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
    return ""


def http_json(url: str, *, headers: dict[str, str], timeout: int = 20) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def brave_search(query: str, *, count: int = 5) -> list[SearchResult]:
    api_key = read_secret_env("BRAVE_API_KEY", "OPENCLAW_BRAVE_API_KEY")
    if not api_key:
        raise RuntimeError("missing_brave_api_key")
    params = urllib.parse.urlencode({"q": query, "count": count, "text_decorations": "false"})
    payload = http_json(
        f"{BRAVE_ENDPOINT}?{params}",
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "X-Subscription-Token": api_key,
            "User-Agent": USER_AGENT,
        },
    )
    raw_results = ((payload.get("web") or {}).get("results") or [])[:count]
    results: list[SearchResult] = []
    for item in raw_results:
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        results.append(
            SearchResult(
                title=html.unescape(str(item.get("title") or url).strip()),
                url=url,
                snippet=html.unescape(str(item.get("description") or "").strip()),
            )
        )
    return results


def extract_urls(text: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for match in URL_RE.finditer(text or ""):
        url = match.group(0).rstrip("。,.，、)")
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def html_to_text(raw_html: str) -> tuple[str, str]:
    title_match = re.search(r"<title[^>]*>([\s\S]*?)</title>", raw_html, re.IGNORECASE)
    title = html.unescape(TAG_RE.sub("", title_match.group(1)).strip()) if title_match else ""
    body = SCRIPT_STYLE_RE.sub(" ", raw_html)
    body = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", body)
    text = html.unescape(TAG_RE.sub(" ", body))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return title[:200], text.strip()[:6000]


def fetch_page(url: str, *, timeout: int = 20) -> FetchResult:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200))
            raw = resp.read(700_000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return FetchResult(url=url, ok=False, status=exc.code, error=f"HTTP {exc.code}")
    except Exception as exc:
        return FetchResult(url=url, ok=False, error=f"{type(exc).__name__}: {exc}")
    title, text = html_to_text(raw)
    return FetchResult(url=url, ok=bool(text), status=status, title=title, text=text, error="" if text else "empty_text")


def browser_fallback(url: str, *, timeout: int = 30) -> tuple[bool, str]:
    helper = _HERE / "helpers" / "browser_cdp_human.py"
    if not helper.is_file():
        return False, "browser_helper_missing"
    try:
        opened = subprocess.run([sys.executable, str(helper), "open", url], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        if opened.returncode != 0:
            return False, (opened.stdout or "").strip()[:500] or f"browser_open_exit_{opened.returncode}"
        inspected = subprocess.run([sys.executable, str(helper), "inspect", "--target", "latest"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        if inspected.returncode != 0:
            return False, (inspected.stdout or "").strip()[:500] or f"browser_inspect_exit_{inspected.returncode}"
        return True, (inspected.stdout or "").strip()[:2000]
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def choose_query(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    cleaned = re.sub(r"^(汤猴[,，\s]*)?", "", cleaned)
    return cleaned[:300] or "public information query"


def summarize_with_model(query: str, fetched: list[FetchResult]) -> str:
    source_pack = "\n\n".join(
        f"Source {idx + 1}: {item.title or item.url}\nURL: {item.url}\nContent:\n{item.text[:1500]}"
        for idx, item in enumerate(fetched[:3])
    )
    if not source_pack:
        return ""
    messages = [
        {
            "role": "system",
            "content": "You are OpenClaw researchWorker. Summarize public web sources in concise Chinese. Do not invent facts. Return 3-5 bullets only.",
        },
        {"role": "user", "content": f"Query: {query}\n\nSources:\n{source_pack}"},
    ]
    try:
        content, _meta = call_model(messages, timeout=30, temperature=0)
        return content.strip()[:1800]
    except Exception:
        return ""


def deterministic_summary(query: str, search_results: list[SearchResult], fetched: list[FetchResult]) -> str:
    lines = [f"查询：{query}", "要点："]
    if fetched:
        for item in fetched[:3]:
            title = item.title or next((r.title for r in search_results if r.url == item.url), item.url)
            preview = re.sub(r"\s+", " ", item.text).strip()[:180]
            lines.append(f"- {title}：{preview}")
    elif search_results:
        for item in search_results[:3]:
            lines.append(f"- {item.title}：{item.snippet or item.url}")
    else:
        lines.append("- 没有可整理的公开来源内容。")
    return "\n".join(lines)


def format_reply(query: str, evidence: ResearchEvidence, fetched: list[FetchResult], *, status: str, reason: str = "") -> str:
    sources = evidence.sources
    if status == "success":
        model_summary = summarize_with_model(query, fetched)
        summary = model_summary or deterministic_summary(query, [], fetched)
        lines = ["联网检索结果", "状态：成功", summary, "来源："]
        for idx, source in enumerate(sources[:5], 1):
            lines.append(f"{idx}. {source.get('title') or source.get('url')} - {source.get('url')}")
    else:
        lines = ["联网检索未完成", "状态：失败", f"原因：{reason or evidence.search_error or evidence.browser_error or 'unknown'}"]
    lines.append(
        "检索证据："
        f"search_attempted={str(evidence.search_attempted).lower()} "
        f"fetch_attempted={str(evidence.fetch_attempted).lower()} "
        f"browser_attempted={str(evidence.browser_attempted).lower()} "
        f"sources={len(sources)}"
    )
    return "\n".join(lines)


def run_research(text: str) -> tuple[int, str, ResearchEvidence]:
    query = choose_query(text)
    evidence = ResearchEvidence(query=query, provider="brave")
    urls = extract_urls(text)
    search_results: list[SearchResult] = []
    if urls:
        search_results = [SearchResult(title=url, url=url) for url in urls]
        evidence.provider = "direct_url"
    else:
        evidence.search_attempted = True
        try:
            search_results = brave_search(query)
        except Exception as exc:
            evidence.search_error = f"{type(exc).__name__}: {exc}"
            append_jsonl(invocation_log_path(), {"created_at": utc_now(), **asdict(evidence)})
            return 4, format_reply(query, evidence, [], status="failed", reason=evidence.search_error), evidence
    evidence.candidates = [asdict(item) for item in search_results]
    fetched: list[FetchResult] = []
    for result in search_results[:5]:
        evidence.fetch_attempted = True
        fetched_item = fetch_page(result.url)
        evidence.fetches.append(asdict(fetched_item))
        if fetched_item.ok:
            fetched.append(fetched_item)
            evidence.sources.append({"title": fetched_item.title or result.title, "url": result.url})
        if len(fetched) >= 3:
            break
    if not fetched and search_results:
        evidence.browser_attempted = True
        ok, browser_result = browser_fallback(search_results[0].url)
        evidence.browser_error = "" if ok else browser_result
        if ok:
            evidence.sources.append({"title": search_results[0].title, "url": search_results[0].url})
            fetched.append(FetchResult(search_results[0].url, True, title=search_results[0].title, text=browser_result))
    status = "success" if evidence.sources else "failed"
    reason = "" if evidence.sources else evidence.search_error or evidence.browser_error or "no_fetchable_sources"
    reply = format_reply(query, evidence, fetched, status=status, reason=reason)
    append_jsonl(invocation_log_path(), {"created_at": utc_now(), **asdict(evidence)})
    return (0 if status == "success" else 5), reply, evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--message-timestamp", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    code, reply, _evidence = run_research(args.text)
    print(reply)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
