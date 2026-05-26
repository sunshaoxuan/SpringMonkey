#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint


HOST = "ccnode.briconbric.com"
PORT = 8822
USER = "root"


REMOTE = r"""
set -e
python3 - <<'PY'
import hashlib
import json
from pathlib import Path

errors = []


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12] if value else "empty"


def key_info(label: str, value: str) -> None:
    print(f"{label}: present={bool(value)} len={len(value)} sha12={digest(value)}")


secret_path = Path("/etc/openclaw/secrets/news_codex_api_key")
secret = secret_path.read_text(encoding="utf-8").strip() if secret_path.is_file() else ""
key_info("secret.news_codex_api_key", secret)
if not secret:
    errors.append("missing shared codex key file")

env_path = Path("/etc/openclaw/openclaw.env")
env_values = {}
if env_path.is_file():
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, value = line.split("=", 1)
        env_values[key.strip()] = value.strip().strip('"').strip("'")
print(f"env.NEWS_CODEX_BASE_URL={env_values.get('NEWS_CODEX_BASE_URL')}")
print(f"env.OPENCLAW_PUBLIC_MODEL_BASE_URL={env_values.get('OPENCLAW_PUBLIC_MODEL_BASE_URL')}")
print(f"env.OPENCLAW_MODEL_FALLBACK_BASE_URL={env_values.get('OPENCLAW_MODEL_FALLBACK_BASE_URL')}")
print(f"env.OPENCLAW_QWEN_FALLBACK_BASE_URL={env_values.get('OPENCLAW_QWEN_FALLBACK_BASE_URL')}")
for key in ("NEWS_CODEX_BASE_URL", "OPENCLAW_PUBLIC_MODEL_BASE_URL"):
    value = env_values.get(key, "")
    if value and "ccnode.briconbric.com:49530/v1" not in value:
        errors.append(f"unexpected primary model endpoint {key}={value}")
for key in ("OPENCLAW_MODEL_FALLBACK_BASE_URL", "OPENCLAW_QWEN_FALLBACK_BASE_URL", "OLLAMA_BASE_URL"):
    value = env_values.get(key, "")
    if value and "ccnode.briconbric.com:22545" not in value:
        errors.append(f"unexpected fallback model endpoint {key}={value}")

config_paths = [
    Path("/var/lib/openclaw/.openclaw/openclaw.json"),
    Path("/root/.openclaw/openclaw.json"),
]
profile_paths = [
    Path("/var/lib/openclaw/.openclaw/agents/main/agent/auth-profiles.json"),
    Path("/root/.openclaw/agents/main/agent/auth-profiles.json"),
]

for path in config_paths:
    print(f"--- config {path}")
    if not path.is_file():
        errors.append(f"missing config {path}")
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    providers = ((data.get("models") or {}).get("providers") or {})
    openai = providers.get("openai") or {}
    base = str(openai.get("baseUrl") or "")
    key = str(openai.get("apiKey") or "")
    print(f"openai.baseUrl={base}")
    key_info(f"{path}.openai.apiKey", key)
    if base and "ccnode.briconbric.com:49530" in base:
        errors.append(f"openai provider must not point at ccnode because image generation uses ChatGPT/OAuth path in {path}")
    ollama = providers.get("ollama") or {}
    ollama_base = str(ollama.get("baseUrl") or "")
    print(f"ollama.baseUrl={ollama_base}")
    if ollama_base and "ccnode.briconbric.com:22545" not in ollama_base:
        errors.append(f"unexpected ollama baseUrl in {path}: {ollama_base}")

for path in profile_paths:
    print(f"--- auth {path}")
    if not path.is_file():
        errors.append(f"missing auth profile {path}")
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    profiles = data.get("profiles") or {}
    order = data.get("order") or {}
    last_good = data.get("lastGood") or {}
    print(f"order.openai={order.get('openai')}")
    print(f"lastGood.openai={last_good.get('openai')}")
    profile = profiles.get("openai:ccnode-codex") or {}
    key = str(profile.get("key") or "")
    key_info(f"{path}.openai:ccnode-codex.key", key)
    if secret and key != secret:
        errors.append(f"openai auth profile key mismatch in {path}")
    if "openai-codex:default" not in profiles:
        errors.append(f"openai-codex oauth profile missing in {path}")
    if last_good.get("openai") == "openai:ccnode-codex":
        errors.append(f"openai lastGood should not force ccnode api key profile in {path}")

if errors:
    print("model_auth_profiles_failed")
    for item in errors:
        print(f"ERROR {item}")
    raise SystemExit(1)
print("model_auth_profiles_ok")
PY
"""


def main() -> int:
    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    try:
        import paramiko
    except ImportError:
        print("paramiko is required for remote verification", file=sys.stderr)
        return 1
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=20)
    try:
        _, stdout, stderr = client.exec_command(REMOTE, get_pty=True, timeout=120)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
    finally:
        client.close()
    if out:
        print(out)
    if err.strip():
        print(err, file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
