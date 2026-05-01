#!/usr/bin/env python3
"""
RSS 新闻发现 + HTTP 正文抓取。

给流水线提供真实文章内容，取代工人模型自行编造。
不依赖任何 API key，只用公开 RSS 和 HTTP。
"""
from __future__ import annotations

import html
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse


RSS_FEEDS: dict[str, list[str]] = {
    "japan": [
        "https://www.japantimes.co.jp/feed/",
        "https://feeds.bbci.co.uk/news/world/asia/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    ],
    "china": [
        "https://feeds.bbci.co.uk/news/world/asia/china/rss.xml",
        "https://www.cnbc.com/id/100727362/device/rss/rss.html",
        "https://feeds.bbci.co.uk/news/world/asia/rss.xml",
    ],
    "us": [
        "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
        "https://feeds.npr.org/1003/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/US.xml",
        "https://www.cnbc.com/id/15837362/device/rss/rss.html",
    ],
    "europe": [
        "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Europe.xml",
        "https://www.politico.eu/feed/",
    ],
    "technology": [
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "https://www.theverge.com/rss/index.xml",
        "https://techcrunch.com/feed/",
        "https://www.engadget.com/rss.xml",
        "https://36kr.com/feed",
    ],
    "entertainment": [
        "https://variety.com/feed/",
        "https://deadline.com/feed/",
        "https://www.hollywoodreporter.com/feed/",
        "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    ],
    "world": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.npr.org/1001/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
    ],
    "markets": [
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://www.cnbc.com/id/10001147/device/rss/rss.html",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
    ],
}

FETCH_TIMEOUT = 15
MAX_ARTICLES_PER_FEED = 12
MAX_CONTENT_CHARS = 3000
MIN_DEGRADED_SNIPPET_CHARS = 10

USER_AGENT = "SpringMonkey/1.0 (news-pipeline)"

BLOCKED_DOMAINS = {"theguardian.com", "www.theguardian.com"}
AGGREGATOR_DOMAINS = {"news.google.com", "google.com", "news.yahoo.com", "yahoo.com"}

JAPAN_KEYWORDS = (
    "japan",
    "japanese",
    "tokyo",
    "osaka",
    "kyoto",
    "hokkaido",
    "yen",
    "nikkei",
    "jpx",
)

CHINA_KEYWORDS = (
    "china",
    "chinese",
    "beijing",
    "shanghai",
    "shenzhen",
    "hong kong",
    "hongkong",
    "taiwan",
    "yuan",
    "renminbi",
)

US_KEYWORDS = (
    "united states",
    "u.s.",
    "us ",
    "america",
    "american",
    "washington",
    "new york",
    "california",
    "美国",
    "华盛顿",
    "纽约",
)

EUROPE_KEYWORDS = (
    "europe",
    "european",
    "eu ",
    "britain",
    "uk ",
    "france",
    "germany",
    "italy",
    "spain",
    "brussels",
    "欧洲",
    "欧盟",
    "英国",
    "法国",
    "德国",
)

TECHNOLOGY_KEYWORDS = (
    "technology",
    "tech",
    "ai",
    "artificial intelligence",
    "semiconductor",
    "chip",
    "software",
    "startup",
    "cyber",
    "科技",
    "人工智能",
    "半导体",
    "芯片",
    "创业",
)

ENTERTAINMENT_KEYWORDS = (
    "entertainment",
    "movie",
    "film",
    "music",
    "tv",
    "streaming",
    "celebrity",
    "hollywood",
    "anime",
    "game",
    "娱乐",
    "电影",
    "音乐",
    "影视",
    "动漫",
    "游戏",
)

DEFAULT_KEYWORDS_BY_BATCH = {
    "japan": JAPAN_KEYWORDS,
    "china": CHINA_KEYWORDS,
    "us": US_KEYWORDS,
    "europe": EUROPE_KEYWORDS,
    "technology": TECHNOLOGY_KEYWORDS,
    "entertainment": ENTERTAINMENT_KEYWORDS,
}


@dataclass
class Article:
    title: str
    url: str
    source_feed: str
    snippet: str = ""
    published_at: str = ""
    published_ts: int = 0
    fingerprint: str = ""
    content: str = ""
    batch_id: str = ""
    fetch_ok: bool = False
    fetch_error: str = ""


def _is_blocked(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
        return any(host.endswith(d) for d in BLOCKED_DOMAINS | AGGREGATOR_DOMAINS)
    except Exception:
        return False


def _parse_published_ts(value: str) -> int:
    raw = (value or "").strip()
    if not raw:
        return 0
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        pass
    for candidate in (raw, raw.replace("Z", "+00:00")):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except Exception:
            continue
    return 0


def build_article_fingerprint(title: str, url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    norm_title = re.sub(r"\s+", " ", (title or "").strip().lower())
    norm_title = re.sub(r"[^\w\u4e00-\u9fff]+", "", norm_title)
    return f"{host}|{norm_title}"


def _classification_text(title: str, url: str, snippet: str) -> str:
    parsed = urlparse(url or "")
    # 域名代表媒体来源，不代表新闻发生地；只用 path/query 辅助识别分区。
    url_context = f"{parsed.path} {parsed.query}"
    return f"{title} {url_context} {snippet}".lower()


def batch_relevant(
    batch_id: str,
    title: str,
    url: str,
    snippet: str,
    keyword_map: dict[str, list[str] | tuple[str, ...]] | None = None,
) -> bool:
    text = _classification_text(title, url, snippet)
    km = keyword_map or {}
    if batch_id in DEFAULT_KEYWORDS_BY_BATCH or batch_id in km:
        keys = tuple(k.lower() for k in (km.get(batch_id) or DEFAULT_KEYWORDS_BY_BATCH.get(batch_id, ())))
        return any(k in text for k in keys)
    return True


def classify_article_batch(
    current_batch: str,
    title: str,
    url: str,
    snippet: str,
    keyword_map: dict[str, list[str] | tuple[str, ...]] | None = None,
    market_keywords: list[str] | tuple[str, ...] | None = None,
) -> str:
    """逐条新闻归类。区域不命中时归入国际，不做整批搬家。"""
    text = _classification_text(title, url, snippet)
    market_keys = tuple(
        k.lower()
        for k in (
            market_keywords
            or (
                "market",
                "stock",
                "shares",
                "earnings",
                "oil",
                "currency",
                "inflation",
                "央行",
                "股价",
                "市场",
                "油价",
                "通胀",
            )
        )
    )
    if batch_relevant("japan", title, url, snippet, keyword_map):
        return "japan"
    if batch_relevant("china", title, url, snippet, keyword_map):
        return "china"
    if batch_relevant("technology", title, url, snippet, keyword_map):
        return "technology"
    if batch_relevant("entertainment", title, url, snippet, keyword_map):
        return "entertainment"
    if batch_relevant("us", title, url, snippet, keyword_map):
        return "us"
    if batch_relevant("europe", title, url, snippet, keyword_map):
        return "europe"
    if any(k in text for k in market_keys):
        return "markets"
    if current_batch == "markets":
        return "markets"
    return "world"


def _article_priority_score(
    batch_id: str,
    title: str,
    url: str,
    snippet: str,
    source_feed: str,
    published_ts: int,
    priority_keywords: list[str] | tuple[str, ...] | None = None,
) -> int:
    text = f"{title} {url} {snippet}".lower()
    score = 0
    keys = [k.lower() for k in (priority_keywords or []) if isinstance(k, str) and k.strip()]
    if keys and any(k in text for k in keys):
        score += 100
    source = (source_feed or "").lower()
    if "reuters" in source:
        score += 20
    if "bbc" in source:
        score += 12
    if "apnews" in source or "ap-top-news" in source:
        score += 12
    if "npr" in source:
        score += 8
    if batch_id in ("japan", "china") and batch_relevant(batch_id, title, url, snippet):
        score += 10
    if published_ts > 0:
        # 按小时衰减，越新越优先，避免旧闻长期占坑。
        score += min(24, int((published_ts // 3600) % 48))
    return score


def fetch_rss(feed_url: str, timeout: int = FETCH_TIMEOUT) -> list[dict[str, Any]]:
    """Parse an RSS/Atom feed, return list of article dicts with timestamps."""
    req = urllib.request.Request(feed_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception as e:
        print(f"[fetcher] RSS fetch failed {feed_url}: {e}", file=sys.stderr)
        return []

    items: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"[fetcher] RSS parse failed {feed_url}: {e}", file=sys.stderr)
        return []

    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        published_raw = (
            item.findtext("pubDate")
            or item.findtext("{http://purl.org/dc/elements/1.1/}date")
            or ""
        ).strip()
        published_ts = _parse_published_ts(published_raw)
        if title and link and not _is_blocked(link):
            items.append(
                {
                    "title": title,
                    "url": link,
                    "snippet": _strip_html(desc)[:300],
                    "published_at": published_raw,
                    "published_ts": published_ts,
                    "fingerprint": build_article_fingerprint(title, link),
                }
            )

    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = (entry.findtext("atom:title", "", ns) or entry.findtext("title") or "").strip()
            link_el = entry.find("atom:link[@rel='alternate']", ns) or entry.find("atom:link", ns)
            link = (link_el.get("href", "") if link_el is not None else "").strip()
            summary = (entry.findtext("atom:summary", "", ns) or "").strip()
            published_raw = (
                entry.findtext("atom:published", "", ns)
                or entry.findtext("atom:updated", "", ns)
                or entry.findtext("published")
                or entry.findtext("updated")
                or ""
            ).strip()
            published_ts = _parse_published_ts(published_raw)
            if title and link and not _is_blocked(link):
                items.append(
                    {
                        "title": title,
                        "url": link,
                        "snippet": _strip_html(summary)[:300],
                        "published_at": published_raw,
                        "published_ts": published_ts,
                        "fingerprint": build_article_fingerprint(title, link),
                    }
                )

    return items[:MAX_ARTICLES_PER_FEED]


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_article_content(url: str, timeout: int = FETCH_TIMEOUT, max_chars: int = MAX_CONTENT_CHARS) -> str:
    """Fetch a URL and extract main text content from HTML."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(500_000)
            charset = resp.headers.get_content_charset() or "utf-8"
            html_text = raw.decode(charset, errors="replace")
    except Exception as e:
        return f"[fetch_error: {e}]"

    return _extract_main_text(html_text, max_chars)


def _extract_main_text(html_text: str, max_chars: int) -> str:
    """Extract readable text from HTML, focusing on <p>, <h1-h6>, <article> content."""
    for tag in ("script", "style", "nav", "footer", "header", "aside"):
        html_text = re.sub(
            rf"<{tag}[\s>].*?</{tag}>", " ", html_text, flags=re.DOTALL | re.IGNORECASE
        )

    paragraphs: list[str] = []
    pattern = r"<(?:p|h[1-6]|li|figcaption)[^>]*>(.*?)</(?:p|h[1-6]|li|figcaption)>"
    for match in re.finditer(pattern, html_text, re.DOTALL | re.IGNORECASE):
        text = _strip_html(match.group(1)).strip()
        if len(text) > 20:
            paragraphs.append(text)

    result = "\n".join(paragraphs)
    if len(result) > max_chars:
        result = result[:max_chars] + "…"
    return result


def discover_articles(
    batch_id: str,
    feeds: list[str] | None = None,
    max_per_batch: int = 8,
    window_start_ts: int = 0,
    window_end_ts: int = 0,
    exclude_fingerprints: set[str] | None = None,
    require_timestamp: bool = True,
    priority_keywords: list[str] | tuple[str, ...] | None = None,
) -> list[Article]:
    """Discover articles for a batch via RSS feeds."""
    if feeds is None:
        feeds = RSS_FEEDS.get(batch_id, [])

    seen_urls: set[str] = set()
    excluded = exclude_fingerprints or set()
    articles: list[Article] = []
    fallback_articles: list[Article] = []

    for feed_url in feeds:
        items = fetch_rss(feed_url)
        for item in items:
            url = item["url"]
            fingerprint = item.get("fingerprint") or build_article_fingerprint(item.get("title", ""), url)
            if url in seen_urls or fingerprint in excluded:
                continue
            published_ts = int(item.get("published_ts") or 0)
            if window_start_ts and window_end_ts:
                if published_ts:
                    if not (window_start_ts <= published_ts <= window_end_ts):
                        continue
                elif require_timestamp:
                    continue
            candidate = Article(
                title=item["title"],
                url=url,
                source_feed=feed_url,
                snippet=item.get("snippet", ""),
                published_at=item.get("published_at", ""),
                published_ts=published_ts,
                fingerprint=fingerprint,
                batch_id=batch_id,
            )
            if batch_relevant(batch_id, item.get("title", ""), url, item.get("snippet", "")):
                seen_urls.add(url)
                articles.append(candidate)
            else:
                # 软约束：优先按区域关键词匹配；如果整批被筛空，后续回退到未匹配候选，
                # 避免“本节无新闻”的误报。
                fallback_articles.append(candidate)
    if not articles and fallback_articles:
        articles = fallback_articles

    articles.sort(
        key=lambda a: _article_priority_score(
            batch_id,
            a.title,
            a.url,
            a.snippet,
            a.source_feed,
            a.published_ts,
            priority_keywords,
        ),
        reverse=True,
    )
    articles = articles[:max_per_batch]

    return articles


def fetch_and_fill(articles: list[Article], max_chars: int = MAX_CONTENT_CHARS) -> list[Article]:
    """Fetch content for each article in place."""
    for art in articles:
        if art.content:
            continue
        content = fetch_article_content(art.url, max_chars=max_chars)
        snippet = (art.snippet or "").strip()
        degraded = " ".join(x for x in [(art.title or "").strip(), snippet] if x).strip()
        if content.startswith("[fetch_error:"):
            # 降级策略：正文抓取失败时，若 RSS snippet 足够长，仍允许该条进入后续摘要，
            # 避免整批因为站点反爬/临时 5xx 退化为“无合格新增新闻条目”。
            if len(degraded) >= MIN_DEGRADED_SNIPPET_CHARS:
                art.content = degraded
                art.fetch_ok = True
                art.fetch_error = f"{content} [degraded_to_snippet]"
            else:
                art.fetch_error = content
                art.fetch_ok = False
        else:
            art.content = content
            if content.strip():
                art.fetch_ok = True
            elif len(degraded) >= MIN_DEGRADED_SNIPPET_CHARS:
                art.content = degraded
                art.fetch_ok = True
                art.fetch_error = "[fetch_error: empty_extract] [degraded_to_snippet]"
            else:
                art.fetch_ok = False
    return articles


def articles_to_json(articles: list[Article]) -> str:
    return json.dumps([asdict(a) for a in articles], ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RSS news discovery + content fetch")
    parser.add_argument("--batch", default="world", help="Batch ID (japan/china/world/markets)")
    parser.add_argument("--max", type=int, default=5, help="Max articles per batch")
    parser.add_argument("--fetch-content", action="store_true", help="Also fetch article content")
    args = parser.parse_args()

    arts = discover_articles(args.batch, max_per_batch=args.max)
    print(f"Discovered {len(arts)} articles for batch '{args.batch}'")
    if args.fetch_content:
        fetch_and_fill(arts)
    for a in arts:
        status = "OK" if a.fetch_ok else ("SKIP" if not args.fetch_content else "FAIL")
        pub = f" @ {a.published_at}" if a.published_at else ""
        print(f"  [{status}] {a.title[:60]}{pub} — {a.url}")
    if arts:
        print(f"\nSample content ({arts[0].title[:40]}):")
        print(arts[0].content[:500] if arts[0].content else "(no content)")
