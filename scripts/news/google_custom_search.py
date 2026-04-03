#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_LEDGER = Path("/var/lib/openclaw/.openclaw/runtime/google-pse-usage.json")
API_URL = "https://customsearch.googleapis.com/customsearch/v1"


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def today_jst() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()


def ensure_quota(ledger_path: Path, max_calls: int):
    ledger = load_json(ledger_path, {"daily": {}})
    day = today_jst()
    used = int(ledger.get("daily", {}).get(day, 0))
    if used >= max_calls:
        raise SystemExit(
            json.dumps(
                {
                    "ok": False,
                    "error": "quota_exceeded",
                    "provider": "google-programmable-search",
                    "date": day,
                    "used": used,
                    "limit": max_calls,
                },
                ensure_ascii=False,
            )
        )
    return ledger, day, used


def record_usage(ledger_path: Path, ledger: dict, day: str, used: int):
    ledger.setdefault("daily", {})[day] = used + 1
    save_json(ledger_path, ledger)


def main():
    parser = argparse.ArgumentParser(description="Google Programmable Search helper with local daily quota enforcement.")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--num", type=int, default=5, help="Number of results (1-10)")
    parser.add_argument("--site", action="append", default=[], help="Optional site restriction, repeatable")
    parser.add_argument("--ledger", default=str(DEFAULT_LEDGER), help="Usage ledger path")
    parser.add_argument("--max-calls", type=int, default=100, help="Daily max calls")
    args = parser.parse_args()

    api_key = os.environ.get("GOOGLE_CUSTOM_SEARCH_API_KEY", "").strip()
    cx = os.environ.get("GOOGLE_CUSTOM_SEARCH_CX", "").strip()
    if not api_key or not cx:
        raise SystemExit(
            json.dumps(
                {
                    "ok": False,
                    "error": "missing_credentials",
                    "requiredEnv": ["GOOGLE_CUSTOM_SEARCH_API_KEY", "GOOGLE_CUSTOM_SEARCH_CX"],
                },
                ensure_ascii=False,
            )
        )

    query = args.query.strip()
    if args.site:
        site_terms = [f"site:{s.strip()}" for s in args.site if s.strip()]
        if site_terms:
            query = f"{query} {' OR '.join(site_terms)}"

    ledger_path = Path(args.ledger)
    ledger, day, used = ensure_quota(ledger_path, args.max_calls)

    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": max(1, min(args.num, 10)),
        "safe": "off",
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "SpringMonkey/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise SystemExit(
            json.dumps(
                {
                    "ok": False,
                    "error": "request_failed",
                    "provider": "google-programmable-search",
                    "message": str(e),
                },
                ensure_ascii=False,
            )
        )

    record_usage(ledger_path, ledger, day, used)
    items = payload.get("items", []) or []
    result = {
        "ok": True,
        "provider": "google-programmable-search",
        "date": day,
        "used_after": used + 1,
        "limit": args.max_calls,
        "query": query,
        "results": [
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in items
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
