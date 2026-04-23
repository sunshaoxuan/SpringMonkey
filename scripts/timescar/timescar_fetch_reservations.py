#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from task_runtime import TimesCarTaskRuntime


CACHE = Path("/var/lib/openclaw/.openclaw/workspace/state/timescar_entry_candidates.json")
STATE_DIR = Path("/var/lib/openclaw/.openclaw/workspace/state")
STORAGE_STATE = STATE_DIR / "timescar_storage_state.json"
STDERR_LOG = Path("/var/lib/openclaw/.openclaw/logs/timescar_browser.stderr.log")
SECRET_CMD = ["bash", "/var/lib/openclaw/.openclaw/workspace/scripts/timescar_secret.sh"]
LOGIN_PATH = "https://share.timescar.jp/view/member/mypage.jsp"
RESERVE_LIST = "https://share.timescar.jp/view/reserve/list.jsp"
DT_RE = re.compile(r"(\d{4})年(\d{2})月(\d{2})日（[^）]+）(\d{2}):(\d{2})")
CAR_RE = re.compile(r"^(.*?)\s*（(.*?)）$")


def parse_dt(text: str) -> str:
    m = DT_RE.search(text)
    if not m:
        return text.strip()
    y, mo, d, hh, mm = map(int, (m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)))
    return datetime(y, mo, d, hh, mm).isoformat(timespec="minutes")


def load_credentials() -> tuple[str, str, str]:
    data = json.loads(subprocess.check_output(SECRET_CMD, text=True))
    p1, p2 = data["member_number_parts"]
    return p1, p2, data["password"]


def load_candidates() -> list[str]:
    try:
        data = json.loads(CACHE.read_text(encoding="utf-8"))
        urls = [item["url"] for item in data.get("candidates", []) if item.get("url")]
        return urls or [LOGIN_PATH]
    except Exception:
        return [LOGIN_PATH]


def update_cache(url: str, note: str) -> None:
    try:
        data = json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        data = {"version": 1, "updatedAt": "", "candidates": [], "negativeHints": []}
    candidates = [c for c in data.get("candidates", []) if c.get("url") != url]
    candidates.insert(0, {"url": url, "priority": 100, "source": "discovered", "note": note})
    data["candidates"] = candidates[:5]
    data["updatedAt"] = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@contextmanager
def redirect_process_stderr(target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        sys.stderr.flush()
    except Exception:
        pass
    saved_fd = os.dup(2)
    with open(target, "ab", buffering=0) as fh:
        os.dup2(fh.fileno(), 2)
        try:
            yield
        finally:
            try:
                sys.stderr.flush()
            except Exception:
                pass
            os.dup2(saved_fd, 2)
            os.close(saved_fd)


def rows_to_reservations(rows: list[str]) -> list[dict[str, Any]]:
    reservations: list[dict[str, Any]] = []
    i = 0
    while i < len(rows):
        text = rows[i].strip()
        if not re.match(r"^\d{9}\b", text):
            i += 1
            continue
        parts = [p.strip() for p in re.split(r"\t+", text) if p.strip()]
        booking_no = parts[0]
        start_text = parts[1] if len(parts) > 1 else ""
        station = parts[2] if len(parts) > 2 else ""
        vehicle_raw = parts[3] if len(parts) > 3 else ""
        accepted_text = parts[4] if len(parts) > 4 else ""
        eticket = parts[5] if len(parts) > 5 else ""
        insurance = parts[6] if len(parts) > 6 else ""
        return_text = rows[i + 1].strip() if i + 1 < len(rows) else ""
        car_name = vehicle_raw
        car_ident = ""
        car_color = ""
        m = CAR_RE.match(vehicle_raw)
        if m:
            car_name = m.group(1).strip()
            ident = m.group(2).replace("\xa0", " ")
            car_ident = ident
            if "、" in ident:
                left, right = ident.rsplit("、", 1)
                car_ident = left.strip()
                car_color = right.strip()
        if eticket == "加入" and not insurance:
            insurance = "加入"
            eticket = ""
        reservations.append(
            {
                "bookingNumber": booking_no,
                "start": parse_dt(start_text),
                "startText": start_text,
                "return": parse_dt(return_text),
                "returnText": return_text,
                "station": station,
                "vehicle": car_name,
                "carIdentifier": car_ident,
                "carColor": car_color,
                "acceptedAt": parse_dt(accepted_text),
                "acceptedAtText": accepted_text,
                "eTicket": eticket or "",
                "insurance": insurance or "",
            }
        )
        i += 4
    return reservations


def is_login_page(page) -> bool:
    return bool(page.locator("#cardNo1").count() and page.locator("#tpPassword").count())


def ensure_logged_in(page, p1: str, p2: str, password: str) -> None:
    if not is_login_page(page):
        return
    page.fill("#cardNo1", p1)
    page.fill("#cardNo2", p2)
    page.fill("#tpPassword", password)
    page.locator("#doLoginForTp").click(timeout=30000)
    page.wait_for_url("**/view/member/mypage.jsp", timeout=30000)


def fetch(runtime: TimesCarTaskRuntime | None = None) -> dict[str, Any]:
    runtime = runtime or TimesCarTaskRuntime("timescar-fetch-reservations", "read", ttl_seconds=900)
    runtime.start("load-credentials")
    p1, p2, password = load_credentials()
    runtime.record_step(step="load-credentials", status="ok", tool="secret.sh", detail="loaded TimesCar credentials")
    last_exc: Exception | None = None
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with redirect_process_stderr(STDERR_LOG):
        with sync_playwright() as p:
            for attempt in range(5):
                browser = None
                context = None
                page = None
                try:
                    runtime.heartbeat(f"connect-browser-{attempt + 1}", note="connect over CDP")
                    browser = p.chromium.connect_over_cdp("http://127.0.0.1:18800")
                    context = browser.contexts[0] if browser.contexts else None
                    if context is None:
                        raise RuntimeError("openclaw browser backend has no default context")
                    page = context.new_page()
                    page.set_default_timeout(15000)
                    runtime.record_step(step="open-reservation-list", status="running", tool="browser", detail=RESERVE_LIST)
                    page.goto(RESERVE_LIST, wait_until="load", timeout=30000)
                    if is_login_page(page):
                        runtime.record_step(step="login-required", status="running", tool="browser", detail="session requires login")
                        for candidate in load_candidates():
                            try:
                                page.goto(candidate, wait_until="load", timeout=30000)
                                if is_login_page(page):
                                    ensure_logged_in(page, p1, p2, password)
                                    runtime.record_step(step="login-required", status="ok", tool="browser", detail=f"login via {candidate}")
                                    break
                            except Exception as exc:
                                last_exc = exc
                        else:
                            raise RuntimeError("no working TimesCar entry found")
                        context.storage_state(path=str(STORAGE_STATE))
                        page.goto(RESERVE_LIST, wait_until="load", timeout=30000)
                    page.locator("tr").first.wait_for(timeout=10000)
                    update_cache(page.url, "member-flow-ok")
                    rows = page.locator("tr").evaluate_all("els => els.map(el => (el.innerText||'').trim()).filter(Boolean)")
                    reservations = rows_to_reservations(rows)
                    runtime.record_step(
                        step="parse-reservations",
                        status="ok",
                        tool="browser",
                        detail=f"parsed {len(reservations)} reservations",
                        observation=page.url,
                    )
                    runtime.finish("ok", "done", final_message=f"{len(reservations)} reservations fetched")
                    return {"ok": True, "entryUrl": page.url, "title": page.title(), "reservations": reservations}
                except Exception as exc:
                    last_exc = exc
                    runtime.record_step(
                        step=f"attempt-{attempt + 1}",
                        status="failed",
                        tool="browser",
                        detail=str(exc),
                    )
                    if STORAGE_STATE.exists():
                        try:
                            STORAGE_STATE.unlink()
                        except OSError:
                            pass
                    time.sleep(2 + attempt)
                finally:
                    if page is not None:
                        try:
                            page.close()
                        except Exception:
                            pass
    runtime.finish("failed", "fetch-failed", final_message=str(last_exc or "playwright launch failed"))
    raise last_exc if last_exc else RuntimeError("playwright launch failed")


def main() -> int:
    print(json.dumps(fetch(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
