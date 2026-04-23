#!/usr/bin/env python3
import argparse
import json
import os
import socket
import time
from pathlib import Path

STATE_PATH = Path("/var/lib/openclaw/.openclaw/workspace/.secure/timescar_task_state.json")


def now_ms():
    return int(time.time() * 1000)


def load_state():
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def clear_state():
    try:
        STATE_PATH.unlink()
    except FileNotFoundError:
        pass


def is_stale(state, ttl_ms):
    if not state:
        return True
    hb = state.get("heartbeatAtMs") or state.get("startedAtMs") or 0
    return now_ms() - hb > ttl_ms


def cmd_start(args):
    ttl_ms = int(args.ttl_seconds * 1000)
    state = load_state()
    if state and not is_stale(state, ttl_ms):
        print(json.dumps({"ok": False, "reason": "active", "state": state}, ensure_ascii=False))
        return 2
    stale = bool(state)
    new_state = {
        "job": args.job,
        "mode": args.mode,
        "status": "running",
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "startedAtMs": now_ms(),
        "heartbeatAtMs": now_ms(),
        "phase": args.phase or "start",
        "ttlSeconds": args.ttl_seconds,
        "replacedStale": stale,
    }
    save_state(new_state)
    print(json.dumps({"ok": True, "state": new_state}, ensure_ascii=False))
    return 0


def cmd_heartbeat(args):
    state = load_state()
    if not state:
        print(json.dumps({"ok": False, "reason": "missing"}, ensure_ascii=False))
        return 1
    state["heartbeatAtMs"] = now_ms()
    if args.phase:
        state["phase"] = args.phase
    save_state(state)
    print(json.dumps({"ok": True, "state": state}, ensure_ascii=False))
    return 0


def cmd_finish(args):
    state = load_state() or {}
    finished = dict(state)
    finished["status"] = args.status
    finished["finishedAtMs"] = now_ms()
    if args.phase:
        finished["phase"] = args.phase
    clear_state()
    print(json.dumps({"ok": True, "finished": finished}, ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("start")
    p.add_argument("--job", required=True)
    p.add_argument("--mode", choices=["read", "write"], required=True)
    p.add_argument("--ttl-seconds", type=int, default=900)
    p.add_argument("--phase")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("heartbeat")
    p.add_argument("--phase")
    p.set_defaults(func=cmd_heartbeat)

    p = sub.add_parser("finish")
    p.add_argument("--status", choices=["ok", "failed", "skipped"], required=True)
    p.add_argument("--phase")
    p.set_defaults(func=cmd_finish)

    args = ap.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
