#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from task_runtime import TimesCarTaskRuntime


TZ = ZoneInfo("Asia/Tokyo")
FETCH_CMD = ["python3", "/var/lib/openclaw/.openclaw/workspace/scripts/timescar_fetch_reservations.py"]
LOG_PATH = Path("/var/lib/openclaw/.openclaw/logs/timescar_next24h.stderr.log")
DECISIONS_PATH = Path("/var/lib/openclaw/.openclaw/workspace/.secure/timescar_user_decisions.json")


def log_error(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now(TZ).isoformat()}] {msg}\n")


def fail(runtime: TimesCarTaskRuntime, user_message: str, detail: str) -> int:
    log_error(detail)
    runtime.record_step(step="fail", status="failed", tool="subprocess", detail=detail)
    runtime.finish("failed", "failed", final_message=user_message)
    print(user_message)
    return 0


def extract_json(raw: str) -> dict:
    raw = raw.strip()
    if not raw:
        raise ValueError("empty output")
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"(\{[\s\S]*\})\s*$", raw)
    if not m:
        raise ValueError("no trailing json object found")
    return json.loads(m.group(1))


def kept_booking_numbers(now: datetime) -> set[str]:
    if not DECISIONS_PATH.exists():
        return set()
    try:
        data = json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return set()
    kept = set()
    for booking, decision in (data.get("keepBookingNumbers") or {}).items():
        if decision.get("status") != "keep":
            continue
        expires_raw = decision.get("expiresAt")
        if expires_raw:
            try:
                expires = datetime.fromisoformat(expires_raw)
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=TZ)
                if expires < now:
                    continue
            except Exception:
                pass
        kept.add(str(booking))
    return kept


def main() -> int:
    runtime = TimesCarTaskRuntime("timescar-ask-cancel-next24h", "read", ttl_seconds=1800)
    runtime.start("fetch-reservations")
    try:
        raw = subprocess.check_output(FETCH_CMD, text=True, stderr=subprocess.STDOUT)
        runtime.record_step(step="fetch-reservations", status="ok", tool="subprocess", detail="fetched reservation payload")
    except subprocess.CalledProcessError as exc:
        output = (exc.output or "").strip()
        detail = f"fetch_reservations failed with exit {exc.returncode}: {output}\n{traceback.format_exc()}"
        return fail(runtime, "读取预约列表失败，请稍后重试。", detail)
    except Exception:
        return fail(runtime, "读取预约列表失败，请稍后重试。", traceback.format_exc())

    try:
        data = extract_json(raw)
        runtime.record_step(step="parse-fetch-output", status="ok", tool="json", detail="parsed reservations json")
    except Exception:
        return fail(runtime, "解析预约数据失败，请稍后重试。", f"invalid json output:\n{raw}\n{traceback.format_exc()}")

    try:
        reservations = data.get("reservations", [])
        now = datetime.now(TZ)
        deadline = now + timedelta(hours=24)
        kept = kept_booking_numbers(now)
        candidates = []
        for reservation in reservations:
            try:
                start = datetime.fromisoformat(reservation["start"]).astimezone(TZ)
            except Exception:
                continue
            if str(reservation.get("bookingNumber") or "") in kept:
                continue
            if now <= start <= deadline:
                candidates.append((start, reservation))
        runtime.record_step(
            step="filter-next-24h",
            status="ok",
            tool="python",
            detail=f"found {len(candidates)} reservations in next 24h",
        )
        if not candidates:
            # Modified: "Talk like a human" as requested by user
            msg = "🚗 已检查未来 24 小时的 TimesCar 预约列表：目前没有即将开始（24小时内）的订单，无需处理。"
            runtime.finish("skipped", "no-match", final_message=msg)
            print(msg)
            return 0
            
        _, reservation = sorted(candidates, key=lambda item: item[0])[0]
        message = "\n".join(
            [
                "🔔 接下来 24 小时内有一单即将开始的预约，是否需要取消？",
                f'开始：{reservation.get("startText", "")}',
                f'结束：{reservation.get("returnText", "")}',
                f'站点：{reservation.get("station", "")}',
                f'车辆：{reservation.get("vehicle", "")}',
                f'预约编号：{reservation.get("bookingNumber", "")}',
                "\n请回复：**取消这单** 或 **保留这单**",
            ]
        )
        runtime.finish("ok", "notice-ready", final_message=message)
        print(message)
        return 0
    except Exception:
        return fail(runtime, "生成取消提醒失败，请稍后重试。", traceback.format_exc())


if __name__ == "__main__":
    raise SystemExit(main())
