#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


OPENCLAW_HOME = Path(os.environ.get("OPENCLAW_HOME", "/var/lib/openclaw/.openclaw"))
CONFIG = OPENCLAW_HOME / "openclaw.json"
STATE_DIR = OPENCLAW_HOME / "workspace" / ".secure"
LOG_DIR = OPENCLAW_HOME / "logs" / "discord_dm_control"
STATE_PATH = STATE_DIR / "discord_dm_control_state.json"
DECISIONS_PATH = STATE_DIR / "timescar_user_decisions.json"
DM_CHANNEL_ID = os.environ.get("OPENCLAW_OWNER_DM_CHANNEL_ID", "1497009159940608020")
OWNER_USER_ID = os.environ.get("OPENCLAW_OWNER_DISCORD_USER_ID", "999666719356354610")
BOT_USER_ID = os.environ.get("OPENCLAW_DISCORD_BOT_USER_ID", "1483638869739180095")
TZ = ZoneInfo("Asia/Tokyo")


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def discord_token() -> str:
    cfg = read_json(CONFIG, {})
    token = cfg.get("channels", {}).get("discord", {}).get("token")
    if not token:
        raise RuntimeError("missing channels.discord.token")
    return str(token)


def discord_request(method: str, path: str, payload: dict | None = None):
    token = discord_token()
    data = None
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "DiscordBot (openclaw-dm-control, 1.0)",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"https://discord.com/api/v10{path}",
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body) if body else None


def fetch_messages(after: str | None, limit: int = 20) -> list[dict]:
    query = {"limit": str(limit)}
    if after:
        query["after"] = after
    path = f"/channels/{DM_CHANNEL_ID}/messages?{urllib.parse.urlencode(query)}"
    messages = discord_request("GET", path)
    return sorted(messages or [], key=lambda item: int(item["id"]))


def send_dm(content: str) -> None:
    chunks = []
    text = content or ""
    while text:
        chunks.append(text[:1900])
        text = text[1900:]
    for chunk in chunks or [""]:
        discord_request("POST", f"/channels/{DM_CHANNEL_ID}/messages", {"content": chunk})


def latest_booking_number_from_dm() -> str | None:
    for msg in reversed(fetch_messages(after=None, limit=30)):
        author_id = str(msg.get("author", {}).get("id", ""))
        if author_id != BOT_USER_ID:
            continue
        content = str(msg.get("content", ""))
        match = re.search(r"预约编号[：:]\s*([0-9]+)", content)
        if match:
            return match.group(1)
    return None


def load_decisions() -> dict:
    data = read_json(DECISIONS_PATH, {})
    if isinstance(data, dict):
        data.setdefault("keepBookingNumbers", {})
        data.setdefault("events", [])
        return data
    return {"keepBookingNumbers": {}, "events": []}


def remember_keep(content: str, message_id: str) -> str:
    booking = None
    explicit = re.search(r"([0-9]{6,})", content)
    if explicit:
        booking = explicit.group(1)
    if not booking:
        booking = latest_booking_number_from_dm()
    if not booking:
        return "已收到“保留这单”，但没有在最近的提醒里找到预约编号；没有写入保留状态。"

    decisions = load_decisions()
    expires = (datetime.now(TZ) + timedelta(days=3)).isoformat(timespec="seconds")
    decisions["keepBookingNumbers"][booking] = {
        "status": "keep",
        "source": "discord_dm_control",
        "messageId": message_id,
        "recordedAt": now_iso(),
        "expiresAt": expires,
    }
    decisions["events"].append(
        {
            "type": "keep",
            "bookingNumber": booking,
            "messageId": message_id,
            "recordedAt": now_iso(),
        }
    )
    decisions["events"] = decisions["events"][-200:]
    write_json(DECISIONS_PATH, decisions)
    return f"已记录：预约 {booking} 保留。后续 24 小时提醒不会再重复询问这单。"


def classify(content: str) -> str:
    text = content.strip()
    if re.search(r"保留(这|此|该)?单|不取消|不要取消", text):
        return "timescar_keep"
    if re.search(r"取消(这|此|该)?单|取消预约", text):
        return "timescar_cancel"
    if re.search(r"订车|预约|TimesCar|timescar|开始时间|结束时间|往后延|延[迟时]|改到|后天", text, re.I):
        return "timescar_change"
    return "unhandled"


def route_message(message: dict) -> str | None:
    author_id = str(message.get("author", {}).get("id", ""))
    if author_id != OWNER_USER_ID:
        return None
    content = str(message.get("content", "")).strip()
    if not content:
        return None
    intent = classify(content)
    if intent == "timescar_keep":
        return remember_keep(content, str(message["id"]))
    if intent == "timescar_change":
        return (
            "已收到 TimesCar 改时指令，并已写入入站控制日志。\n"
            "当前安全状态：入口路由已工作，但改开始时间/取消部分日期属于真实订单变更，"
            "还没有专用执行器和确认页校验，暂不自动执行，避免误改预约。"
        )
    if intent == "timescar_cancel":
        return (
            "已收到 TimesCar 取消指令，并已写入入站控制日志。\n"
            "当前安全状态：取消预约属于真实订单变更，还没有专用执行器和确认页校验，暂不自动执行。"
        )
    return "已收到私信，但没有匹配到可执行的控制台意图；本次不会静默丢弃。"


def poll_once(max_messages: int) -> dict:
    state = read_json(STATE_PATH, {})
    after = state.get("lastMessageId")
    messages = fetch_messages(str(after) if after else None, limit=max_messages)
    processed = []
    for message in messages:
        message_id = str(message["id"])
        author_id = str(message.get("author", {}).get("id", ""))
        if author_id == BOT_USER_ID:
            state["lastMessageId"] = message_id
            continue
        response = route_message(message)
        if response:
            send_dm(response)
        processed.append(
            {
                "id": message_id,
                "authorId": author_id,
                "content": str(message.get("content", ""))[:500],
                "responded": bool(response),
                "processedAt": now_iso(),
            }
        )
        state["lastMessageId"] = message_id

    state["updatedAt"] = now_iso()
    state.setdefault("events", [])
    state["events"].extend(processed)
    state["events"] = state["events"][-200:]
    write_json(STATE_PATH, state)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / "latest.json").write_text(json.dumps({"processed": processed, "state": state}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"processed": processed, "state": state}


def initialize_cursor() -> dict:
    messages = fetch_messages(after=None, limit=1)
    latest = messages[0]["id"] if messages else None
    state = read_json(STATE_PATH, {})
    if latest:
        state["lastMessageId"] = str(latest)
    state["initializedAt"] = now_iso()
    write_json(STATE_PATH, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--init-cursor", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-messages", type=int, default=20)
    args = parser.parse_args()
    if args.init_cursor:
        print(json.dumps(initialize_cursor(), ensure_ascii=False))
        return 0
    result = poll_once(args.max_messages)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
