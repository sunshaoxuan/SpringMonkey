#!/usr/bin/env python3
"""
Ollama 连续可用性测试脚本。
模仿用户规则：检查 ccnode 端点的 Ollama 是否响应，并记录失败状态。
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "news" / "broadcast.json"
STATE_FILE = Path("/var/lib/openclaw/.openclaw/state/ollama_health.json")

def load_json(p: Path) -> dict:
    if not p.is_file(): return {}
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_json(p: Path, data: dict):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def check_ollama(base_url: str) -> bool:
    url = base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False

def main():
    if not DEFAULT_CONFIG.is_file():
        print(f"Error: {DEFAULT_CONFIG} not found")
        return 1
    
    cfg = load_json(DEFAULT_CONFIG)
    base_url = cfg.get("model", {}).get("ollamaBaseUrl", "http://ccnode.briconbric.com:22545")
    
    state = load_json(STATE_FILE)
    consecutive_failures = state.get("consecutive_failures", 0)
    
    is_ok = check_ollama(base_url)
    
    if is_ok:
        consecutive_failures = 0
        status = "HEALTHY"
    else:
        consecutive_failures += 1
        status = "UNAVAILABLE"
    
    state["last_check"] = time.strftime("%Y-%m-%d %H:%M:%S")
    state["consecutive_failures"] = consecutive_failures
    state["status"] = status
    state["base_url"] = base_url
    
    save_json(STATE_FILE, state)
    
    print(f"Ollama Status: {status}")
    print(f"Consecutive Failures: {consecutive_failures}")
    
    if consecutive_failures >= 3:
        print("POLICY_ACTION: keep Codex primary; Qwen/Ollama fallback is currently unavailable.")
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
