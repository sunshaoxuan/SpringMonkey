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
from dataclasses import asdict, dataclass, field
from typing import Any


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
MAX_ARTICLES_PER_FEED = 5
MAX_CONTENT_CHARS = 3000

USER_AGENT = "SpringMonkey/1.0 (news-pipeline)"

BLOCKED_DOMAINS = {"theguardian.com", "www.theguardian.com"}
AGGREGATOR_DOMAINS = {"news.google.com", "google.com", "news.yahoo.com", "yahoo.com"}


@dataclass
class Article:
    title: str
    url: str
    source_feed: str
    snippet: str = ""
    content: str = ""
    batch_id: str = ""
    fetch_ok: bool = False
    fetch_error: str = ""


def _is_blocked(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        return any(host.endswith(d) for d in BLOCKED_DOMAINS | AGGREGATOR_DOMAINS)
    except Exception:
        return False


def fetch_rss(feed_url: str, timeout: int = FETCH_TIMEOUT) -> list[dict[str, str]]:
    """Parse an RSS/Atom feed, return list of {title, url, snippet}."""
    req = urllib.request.Request(feed_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception as e:
        print(f"[fetcher] RSS fetch failed {feed_url}: {e}", file=sys.stderr)
        return []

    items: list[dict[str, str]] = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"[fetcher] RSS parse failed {feed_url}: {e}", file=sys.stderr)
        return []

    # RSS 2.0
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        if title and link and not _is_blocked(link):
            items.append({"title": title, "url": link, "snippet": _strip_html(desc)[:300]})

    # Atom
    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = (entry.findtext("atom:title", "", ns) or entry.findtext("title") or "").strip()
            link_el = entry.find("atom:link[@rel='alternate']", ns) or entry.find("atom:link", ns)
            link = (link_el.get("href", "") if link_el is not None else "").strip()
            summary = (entry.findtext("atom:summary", "", ns) or "").strip()
            if title and link and not _is_blocked(link):
                items.append({"title": title, "url": link, "snippet": _strip_html(summary)[:300]})

    return items[:MAX_ARTICLES_PER_FEED]


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_article_content(url: str, timeout: int = FETCH_TIMEOUT, max_chars: int = MAX_CONTENT_CHARS) -> str:
    """Fetch a URL and extract main text content from HTML."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    })
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

    for m in re.finditer(r"<(?:p|h[1-6]|li|figcaption)[^>]*>(.*?)</(?:p|h[1-6]|li|figcaption)>",
                         html_text, re.DOTALL | re.IGNORECASE):
        text = _strip_html(m.group(1)).strip()
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
) -> list[Article]:
    """Discover articles for a batch via RSS feeds."""
    if feeds is None:
        feeds = RSS_FEEDS.get(batch_id, [])

    seen_urls: set[str] = set()
    articles: list[Article] = []

    for feed_url in feeds:
        items = fetch_rss(feed_url)
        for item in items:
            url = item["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            articles.append(Article(
                title=item["title"],
                url=url,
                source_feed=feed_url,
                snippet=item.get("snippet", ""),
                batch_id=batch_id,
            ))
            if len(articles) >= max_per_batch:
                break
        if len(articles) >= max_per_batch:
            break

    return articles


def fetch_and_fill(articles: list[Article], max_chars: int = MAX_CONTENT_CHARS) -> list[Article]:
    """Fetch content for each article in place."""
    for art in articles:
        if art.content:
            continue
        content = fetch_article_content(art.url, max_chars=max_chars)
        if content.startswith("[fetch_error:"):
            art.fetch_error = content
            art.fetch_ok = False
        else:
            art.content = content
            art.fetch_ok = bool(content.strip())
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
        print(f"  [{status}] {a.title[:60]} — {a.url}")
    if arts:
        print(f"\nSample content ({arts[0].title[:40]}):")
        print(arts[0].content[:500] if arts[0].content else "(no content)")
