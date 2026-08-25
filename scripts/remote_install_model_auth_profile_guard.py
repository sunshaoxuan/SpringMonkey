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
install -d -m 755 /usr/local/lib/openclaw
install -d -m 755 /etc/systemd/system/openclaw.service.d
cat >/usr/local/lib/openclaw/ensure_model_auth_profiles.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
sleep "${OPENCLAW_AUTH_PROFILE_GUARD_DELAY:-0}"
python3 - <<'PY'
import json
import os
import pwd
import shutil
from datetime import datetime, timezone
from pathlib import Path

config_paths = [
    Path("/var/lib/openclaw/.openclaw/openclaw.json"),
    Path("/root/.openclaw/openclaw.json"),
]
profile_paths = [
    Path("/var/lib/openclaw/.openclaw/agents/main/agent/auth-profiles.json"),
    Path("/root/.openclaw/agents/main/agent/auth-profiles.json"),
]

secret_path = Path("/etc/openclaw/secrets/news_codex_api_key")


def read_existing_codex_token() -> str:
    if secret_path.is_file():
        return secret_path.read_text(encoding="utf-8").strip()
    for path in config_paths:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        providers = data.get("models", {}).get("providers", {})
        for provider_id in ("openai-codex", "openai"):
            token = str((providers.get(provider_id) or {}).get("apiKey") or "").strip()
            if token:
                return token
    return ""


secret = read_existing_codex_token()
if not secret:
    raise SystemExit("[model-auth-profile-guard] missing codex token in secret file and OpenClaw config")

secret_path.parent.mkdir(parents=True, exist_ok=True)
if not secret_path.exists() or secret_path.read_text(encoding="utf-8").strip() != secret:
    secret_path.write_text(secret + "\n", encoding="utf-8")
    secret_path.chmod(0o640)
    try:
        user = pwd.getpwnam("openclaw")
        os.chown(secret_path, 0, user.pw_gid)
    except Exception:
        pass


def backup(path: Path) -> None:
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, path.with_suffix(path.suffix + f".bak-model-auth-{stamp}"))


def write_json_if_changed(path: Path, data: dict) -> bool:
    def ensure_openclaw_owner() -> None:
        if str(path).startswith("/var/lib/openclaw/"):
            try:
                user = pwd.getpwnam("openclaw")
                os.chown(path, user.pw_uid, user.pw_gid)
            except Exception:
                pass

    rendered = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old == rendered:
        ensure_openclaw_owner()
        return False
    backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    path.chmod(0o600)
    ensure_openclaw_owner()
    return True


for path in config_paths:
    if not path.exists():
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    providers = data.setdefault("models", {}).setdefault("providers", {})
    openai = providers.get("openai")
    if isinstance(openai, dict) and "ccnode.briconbric.com:49530" in str(openai.get("baseUrl", "")):
        openai.pop("baseUrl", None)
        openai.pop("apiKey", None)
        openai.pop("models", None)
    providers["openai-codex"] = {
        "api": "openai-completions",
        "apiKey": secret,
        "baseUrl": "http://ccnode.briconbric.com:49530/v1",
        "models": [
            {
                "id": "gpt-5.6-sol",
                "name": "GPT-5.6 Sol via ccnode",
                "reasoning": True,
                "input": ["text", "image"],
                "contextWindow": 196000,
                "maxTokens": 32768,
            },
            {
                "id": "gpt-5.5",
                "name": "GPT-5.5 via ccnode",
                "reasoning": True,
                "input": ["text", "image"],
                "contextWindow": 196000,
                "maxTokens": 32768,
            },
            {
                "id": "gpt-5.4",
                "name": "GPT-5.4 via ccnode",
                "reasoning": True,
                "input": ["text", "image"],
                "contextWindow": 196000,
                "maxTokens": 32768,
            },
        ],
    }
    defaults = data.setdefault("agents", {}).setdefault("defaults", {}).setdefault("model", {})
    defaults["primary"] = "openai-codex/gpt-5.6-sol"
    configured_models = data.setdefault("agents", {}).setdefault("defaults", {}).setdefault("models", {})
    configured_models.setdefault("openai-codex/gpt-5.6-sol", {})
    configured_models.setdefault("openai-codex/gpt-5.5", {})
    configured_models.setdefault("openai-codex/gpt-5.4", {})
    fallbacks = defaults.setdefault("fallbacks", [])
    if "ollama/qwen3:14b" not in fallbacks:
        fallbacks.insert(0, "ollama/qwen3:14b")
    if write_json_if_changed(path, data):
        print(f"[model-auth-profile-guard] updated config {path}")

for path in profile_paths:
    data = {"version": 1, "profiles": {}, "order": {}, "lastGood": {}}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except Exception:
            pass
    data.setdefault("version", 1)
    profiles = data.setdefault("profiles", {})
    profiles["openai:ccnode-codex"] = {
        "provider": "openai",
        "type": "token",
        "key": secret,
        "displayName": "ccnode gpt-5.6-sol",
        "copyToAgents": True,
    }
    profiles["openai-codex:default"] = {
        "provider": "openai-codex",
        "type": "token",
        "key": secret,
        "displayName": "ccnode gpt-5.6-sol",
        "copyToAgents": True,
    }
    profiles["ollama:default"] = {
        "provider": "ollama",
        "type": "api_key",
        "key": "ccnode-ollama-local",
        "displayName": "ccnode ollama",
        "copyToAgents": True,
    }
    order = data.setdefault("order", {})
    order["openai"] = [item for item in order.get("openai", []) if item != "openai:ccnode-codex"]
    order["ollama"] = ["ollama:default"] + [item for item in order.get("ollama", []) if item != "ollama:default"]
    last_good = data.setdefault("lastGood", {})
    if last_good.get("openai") == "openai:ccnode-codex":
        last_good.pop("openai", None)
    last_good["ollama"] = "ollama:default"
    if write_json_if_changed(path, data):
        print(f"[model-auth-profile-guard] updated profile {path}")
print("[model-auth-profile-guard] ok")
PY

secret_tmp="$(mktemp /tmp/openclaw-model-auth-token.XXXXXX)"
chmod 600 "$secret_tmp"
trap 'rm -f "$secret_tmp"' EXIT
python3 - "$secret_tmp" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
secret_path = Path("/etc/openclaw/secrets/news_codex_api_key")
secret = secret_path.read_text(encoding="utf-8").strip() if secret_path.is_file() else ""
if not secret:
    for path in [Path("/var/lib/openclaw/.openclaw/openclaw.json"), Path("/root/.openclaw/openclaw.json")]:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        providers = data.get("models", {}).get("providers", {})
        secret = str((providers.get("openai-codex") or {}).get("apiKey") or (providers.get("openai") or {}).get("apiKey") or "").strip()
        if secret:
            break
if not secret:
    raise SystemExit("missing codex token for sqlite auth sync")
out.write_text(secret, encoding="utf-8")
PY

sync_auth_profile() {
  local mode="$1"
  local provider="$2"
  local profile_id="$3"
  local source_file="$4"
  local command=(openclaw --no-color models auth --agent main "$mode" --provider "$provider" --profile-id "$profile_id")
  OPENCLAW_STATE_DIR=/var/lib/openclaw/.openclaw \
  OPENCLAW_CONFIG_PATH=/var/lib/openclaw/.openclaw/openclaw.json \
  timeout 90 "${command[@]}" <"$source_file" >/tmp/openclaw-auth-sync-"$provider".out 2>/tmp/openclaw-auth-sync-"$provider".err \
    || {
      rc=$?
      echo "[model-auth-profile-guard] sqlite auth sync failed provider=$provider rc=$rc" >&2
      sed -E 's/[A-Za-z0-9_=-]{20,}/<redacted>/g' /tmp/openclaw-auth-sync-"$provider".err >&2 || true
    }
}

if command -v openclaw >/dev/null 2>&1; then
  sync_auth_profile paste-token openai openai:ccnode-codex "$secret_tmp"
  sync_auth_profile paste-token openai-codex openai-codex:default "$secret_tmp"
  printf '%s\n' 'ccnode-ollama-local' >/tmp/openclaw-ollama-auth-placeholder
  sync_auth_profile paste-api-key ollama ollama:default /tmp/openclaw-ollama-auth-placeholder
  rm -f /tmp/openclaw-ollama-auth-placeholder
fi
EOF
chmod 755 /usr/local/lib/openclaw/ensure_model_auth_profiles.sh

cat >/etc/systemd/system/openclaw.service.d/35-model-auth-profile-guard.conf <<'EOF'
[Service]
ExecStartPost=/bin/bash -lc 'OPENCLAW_AUTH_PROFILE_GUARD_DELAY=20 /usr/local/lib/openclaw/ensure_model_auth_profiles.sh'
EOF

cat >/etc/systemd/system/openclaw-model-auth-profile-guard.service <<'EOF'
[Unit]
Description=Repair OpenClaw model auth profile drift
After=openclaw.service

[Service]
Type=oneshot
ExecStart=/usr/local/lib/openclaw/ensure_model_auth_profiles.sh
EOF

systemctl daemon-reload
OPENCLAW_AUTH_PROFILE_GUARD_DELAY=0 /usr/local/lib/openclaw/ensure_model_auth_profiles.sh
systemctl disable --now openclaw-model-auth-profile-guard.timer 2>/dev/null || true
systemctl restart openclaw.service
sleep 35
systemctl is-active openclaw.service
OPENCLAW_AUTH_PROFILE_GUARD_DELAY=0 /usr/local/lib/openclaw/ensure_model_auth_profiles.sh
echo "=== drop-in ==="
systemctl cat openclaw.service | sed -n '/35-model-auth-profile-guard.conf/,+5p'
echo "=== timer ==="
systemctl is-enabled openclaw-model-auth-profile-guard.timer 2>/dev/null || true
systemctl list-timers openclaw-model-auth-profile-guard.timer --no-pager || true
echo DONE
"""


def main() -> int:
    pw = load_openclaw_ssh_password()
    if not pw:
        print(missing_password_hint(), file=sys.stderr)
        return 1
    try:
        import paramiko
    except ImportError:
        print("paramiko is required for remote installation", file=sys.stderr)
        return 1
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=20)
    try:
        _, stdout, stderr = client.exec_command(REMOTE, get_pty=True, timeout=240)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
    finally:
        client.close()
    if out:
        print(out)
    if err.strip():
        print(err, file=sys.stderr)
    return 0 if rc == 0 and "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
