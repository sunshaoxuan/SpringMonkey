#!/usr/bin/env python3
"""Enable Gemini Pro as the explicit model fallback after a live smoke test."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint


HOST = os.environ.get("OPENCLAW_SSH_HOST", "ccnode.briconbric.com")
PORT = int(os.environ.get("OPENCLAW_SSH_PORT", "8822"))
USER = os.environ.get("OPENCLAW_SSH_USER", "root")
MODEL = os.environ.get("OPENCLAW_GEMINI_FALLBACK_MODEL", "gemini-pro-agent")
BASE_URL = os.environ.get("OPENCLAW_GEMINI_FALLBACK_BASE_URL", "http://ccnode.briconbric.com:49530/v1")


REMOTE = r"""
set -euo pipefail

MODEL="__MODEL__"
BASE_URL="__BASE_URL__"
ENV_FILE="/etc/openclaw/openclaw.env"
CONFIG_PATH="/var/lib/openclaw/.openclaw/openclaw.json"
ROOT_CONFIG_PATH="/root/.openclaw/openclaw.json"
KEY_FILE="/etc/openclaw/secrets/news_codex_api_key"

python3 - "$MODEL" "$BASE_URL" <<'PY'
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

model, base_url = sys.argv[1], sys.argv[2].rstrip("/")
key = ""
for path in [
    Path("/run/credentials/openclaw.service/openclaw-secrets.json"),
    Path("/etc/openclaw/openclaw-secrets.json"),
]:
    if not path.exists():
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    node = data.get("providers", {}).get("openaiCodex")
    if isinstance(node, dict) and node.get("apiKey"):
        key = str(node["apiKey"])
        break
if not key and Path("/etc/openclaw/secrets/news_codex_api_key").is_file():
    key = Path("/etc/openclaw/secrets/news_codex_api_key").read_text(encoding="utf-8").strip()
if not key:
    print("GEMINI_FALLBACK_NOT_ENABLED missing_codex_key")
    raise SystemExit(2)

payload = {
    "model": model,
    "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
    "temperature": 0,
}
req = urllib.request.Request(
    base_url + "/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    method="POST",
)
try:
    data = json.loads(urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace"))
    text = str(data["choices"][0]["message"]["content"]).strip().lower()
except urllib.error.HTTPError as exc:
    detail = exc.read(500).decode("utf-8", "replace").replace("\n", " ")
    print(f"GEMINI_FALLBACK_NOT_ENABLED http_{exc.code} {detail}")
    raise SystemExit(2)
except Exception as exc:
    print(f"GEMINI_FALLBACK_NOT_ENABLED {type(exc).__name__}: {exc}")
    raise SystemExit(2)
if text != "ok":
    print(f"GEMINI_FALLBACK_NOT_ENABLED unexpected_response={text[:120]}")
    raise SystemExit(2)
print("GEMINI_FALLBACK_SMOKE_OK")
PY

python3 - "$MODEL" "$BASE_URL" "$ENV_FILE" "$CONFIG_PATH" "$ROOT_CONFIG_PATH" "$KEY_FILE" <<'PY'
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
import sys

model, base_url = sys.argv[1], sys.argv[2], Path(sys.argv[3])
config_paths = [Path(sys.argv[4]), Path(sys.argv[5])]
key_file = sys.argv[6]

def backup(path: Path) -> None:
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, path.with_suffix(path.suffix + f".bak-gemini-fallback-{stamp}"))

def update_env(path: Path) -> None:
    values = {}
    order = []
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            key, value = line.split("=", 1)
            key = key.strip()
            values[key] = value.strip().strip('"').strip("'")
            if key not in order:
                order.append(key)
    additions = {
        "OPENCLAW_MODEL_FALLBACK_PROVIDER": "openai_compatible",
        "OPENCLAW_MODEL_FALLBACK_BASE_URL": base_url,
        "OPENCLAW_MODEL_FALLBACK": model,
        "OPENCLAW_MODEL_FALLBACK_API_KEY_FILE": key_file,
        "OPENCLAW_INTENT_FALLBACK_BASE_URL": base_url,
        "OPENCLAW_INTENT_FALLBACK_MODELS": model,
        "OPENCLAW_INTENT_FALLBACK_API_KEY_FILE": key_file,
        "NEWS_FALLBACK_MODEL": f"openai-codex/{model}",
    }
    for key, value in additions.items():
        values[key] = value
        if key not in order:
            order.append(key)
    backup(path)
    path.write_text("\n".join([f"{key}={values[key]}" for key in order if key in values]).rstrip() + "\n", encoding="utf-8")

def update_config(path: Path) -> None:
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    provider = data.setdefault("models", {}).setdefault("providers", {}).setdefault("openai-codex", {})
    models = provider.setdefault("models", [])
    if not any(isinstance(item, dict) and item.get("id") == model for item in models):
        models.append({
            "id": model,
            "name": "Gemini Pro Agent via ccnode",
            "reasoning": True,
            "input": ["text", "image"],
            "contextWindow": 196000,
            "maxTokens": 32768,
        })
    defaults = data.setdefault("agents", {}).setdefault("defaults", {})
    defaults.setdefault("model", {})["fallbacks"] = [f"openai-codex/{model}"]
    defaults.setdefault("models", {}).setdefault(f"openai-codex/{model}", {})
    backup(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

update_env(env_file)
for config in config_paths:
    update_config(config)
print(f"GEMINI_FALLBACK_ENABLED model=openai-codex/{model} base_url={base_url}")
PY

systemctl daemon-reload
systemctl restart openclaw.service
sleep 35
systemctl is-active openclaw.service
echo DONE
"""


def main() -> int:
    password = load_openclaw_ssh_password()
    if not password:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    try:
        import paramiko
    except ImportError:
        print("缺少 paramiko。请执行：python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt", file=sys.stderr)
        return 1

    remote = REMOTE.replace("__MODEL__", MODEL).replace("__BASE_URL__", BASE_URL)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=password, timeout=30, allow_agent=False, look_for_keys=False)
    try:
        _, stdout, stderr = client.exec_command(remote, get_pty=True, timeout=180)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
    finally:
        client.close()
    if out:
        print(out)
    if err.strip():
        print(err, file=sys.stderr)
    return 0 if rc == 0 and "DONE" in out else rc


if __name__ == "__main__":
    raise SystemExit(main())
