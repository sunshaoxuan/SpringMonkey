#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
from typing import Any

errors = []


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12] if value else "empty"


def key_info(label: str, value: str) -> None:
    print(f"{label}: present={bool(value)} len={len(value)} sha12={digest(value)}")


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
    if value:
        errors.append(f"fallback model endpoint must be empty after 22545 retirement: {key}={value}")

config_paths = [
    Path("/var/lib/openclaw/.openclaw/openclaw.json"),
    Path("/root/.openclaw/openclaw.json"),
]
profile_paths = [
    Path("/var/lib/openclaw/.openclaw/agents/main/agent/auth-profiles.json"),
    Path("/root/.openclaw/agents/main/agent/auth-profiles.json"),
]


def read_runtime_credential(path_expr: str) -> str:
    credential_path = Path("/run/credentials/openclaw.service/openclaw-secrets.json")
    if not credential_path.is_file():
        return ""
    data: Any = json.loads(credential_path.read_text(encoding="utf-8"))
    for part in path_expr.strip("/").split("/"):
        if not isinstance(data, dict):
            return ""
        data = data.get(part)
    return str(data or "").strip() if isinstance(data, str) else ""


def read_config_codex_token() -> str:
    for path in config_paths:
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        providers = ((data.get("models") or {}).get("providers") or {})
        for provider_id in ("openai-codex", "openai"):
            raw_value = (providers.get(provider_id) or {}).get("apiKey")
            if isinstance(raw_value, str) and raw_value.strip():
                return raw_value.strip()
            if isinstance(raw_value, dict):
                resolved = read_runtime_credential(str(raw_value.get("id") or ""))
                if resolved:
                    return resolved
    return ""


def validate_secret_ref(label: str, value: object, expected_id: str) -> None:
    if isinstance(value, dict):
        print(f"{label}: keyRef id={value.get('id')}")
        if value.get("id") != expected_id:
            errors.append(f"unexpected keyRef for {label}: {value}")
        return
    key = str(value or "")
    key_info(label, key)
    if secret and key != secret:
        errors.append(f"secret mismatch for {label}")


secret_path = Path("/etc/openclaw/secrets/news_codex_api_key")
secret = secret_path.read_text(encoding="utf-8").strip() if secret_path.is_file() else read_config_codex_token()
key_info("secret_or_config.codex_token", secret)
if not secret:
    errors.append("missing shared codex token in secret file, SecretRef runtime credential, and OpenClaw config")

for path in config_paths:
    print(f"--- config {path}")
    if not path.is_file():
        errors.append(f"missing config {path}")
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    providers = ((data.get("models") or {}).get("providers") or {})
    defaults = ((data.get("agents") or {}).get("defaults") or {}).get("model") or {}
    print(f"default.primary={defaults.get('primary')}")
    if defaults.get("primary") != "openai-codex/gpt-5.3-codex-spark":
        errors.append(f"unexpected primary model in {path}: {defaults.get('primary')}")
    print(f"default.fallbacks={defaults.get('fallbacks')}")
    allowed_fallbacks = ([], ["openai-codex/gemini-pro-agent"])
    if defaults.get("fallbacks") not in allowed_fallbacks:
        errors.append(f"model fallbacks must be empty or gemini-pro-agent in {path}: {defaults.get('fallbacks')}")
    codex = providers.get("openai-codex") or {}
    codex_base = str(codex.get("baseUrl") or "")
    codex_key = codex.get("apiKey")
    print(f"openai-codex.baseUrl={codex_base}")
    print(f"openai-codex.timeoutSeconds={codex.get('timeoutSeconds')}")
    validate_secret_ref(f"{path}.openai-codex.apiKey", codex_key, "/providers/openaiCodex/apiKey")
    if "ccnode.briconbric.com:49530/v1" not in codex_base:
        errors.append(f"unexpected openai-codex baseUrl in {path}: {codex_base}")
    if codex.get("timeoutSeconds") != 600:
        errors.append(f"unexpected openai-codex timeoutSeconds in {path}: {codex.get('timeoutSeconds')}")
    codex_models = [item.get("id") for item in codex.get("models", []) if isinstance(item, dict)]
    print(f"openai-codex.models={codex_models}")
    if "gpt-5.6-sol" not in codex_models:
        errors.append(f"missing gpt-5.6-sol model in {path}")
    if "gpt-5.3-codex-spark" not in codex_models:
        errors.append(f"missing gpt-5.3-codex-spark model in {path}")
    if "gemini-pro-agent" not in codex_models:
        errors.append(f"missing gemini-pro-agent model in {path}")
    openai = providers.get("openai") or {}
    base = str(openai.get("baseUrl") or "")
    print(f"openai.baseUrl={base}")
    if base:
        errors.append(f"openai provider must remain empty; use openai-codex provider for ccnode in {path}")
    ollama = providers.get("ollama") or {}
    ollama_base = str(ollama.get("baseUrl") or "")
    print(f"ollama.baseUrl={ollama_base}")
    if ollama_base:
        errors.append(f"OpenClaw chat fallback must not configure ollama after 22545 retirement in {path}: {ollama_base}")

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
    validate_secret_ref(f"{path}.openai:ccnode-codex", profile.get("keyRef") or profile.get("key"), "/providers/openaiCodex/apiKey")
    codex_profile = profiles.get("openai-codex:default") or {}
    validate_secret_ref(f"{path}.openai-codex:default", codex_profile.get("keyRef") or codex_profile.get("key"), "/providers/openaiCodex/apiKey")
    if "openai-codex:default" not in profiles:
        errors.append(f"openai-codex oauth profile missing in {path}")
    if "ollama:default" in profiles:
        errors.append(f"stale ollama auth profile remains in {path}")
    if last_good.get("openai") == "openai:ccnode-codex":
        errors.append(f"openai lastGood should not force ccnode api key profile in {path}")

print("--- sqlite auth store")
import subprocess

auth_cmd = [
    "openclaw",
    "--no-color",
    "models",
    "auth",
    "--agent",
    "main",
    "list",
]
env = {
    **__import__("os").environ,
    "OPENCLAW_STATE_DIR": "/var/lib/openclaw/.openclaw",
    "OPENCLAW_CONFIG_PATH": "/var/lib/openclaw/.openclaw/openclaw.json",
}
result = subprocess.run(auth_cmd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
auth_output = result.stdout
print(auth_output)
for expected in ("openai:ccnode-codex", "openai-codex:default"):
    if expected not in auth_output:
        errors.append(f"missing sqlite auth profile {expected}")
if "ollama:default" in auth_output:
    errors.append("stale sqlite auth profile ollama:default remains")

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

