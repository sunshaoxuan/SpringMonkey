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

credential_path = Path("/run/credentials/openclaw.service/openclaw-secrets.json")
if not credential_path.is_file():
    raise SystemExit("[model-auth-profile-guard] missing systemd credential payload")
file_provider = {
    "source": "file",
    "path": str(credential_path),
    "mode": "json",
    "timeoutMs": 5000,
}
openai_ref = {"source": "file", "provider": "systemd-credential-file", "id": "/providers/openaiCodex/apiKey"}

config_paths = [
    Path("/var/lib/openclaw/.openclaw/openclaw.json"),
    Path("/root/.openclaw/openclaw.json"),
]
profile_paths = [
    Path("/var/lib/openclaw/.openclaw/agents/main/agent/auth-profiles.json"),
    Path("/root/.openclaw/agents/main/agent/auth-profiles.json"),
]


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
    secret_providers = data.setdefault("secrets", {}).setdefault("providers", {})
    secret_providers["systemd-credential-file"] = file_provider
    openai = providers.get("openai")
    if isinstance(openai, dict) and "ccnode.briconbric.com:49530" in str(openai.get("baseUrl", "")):
        openai.pop("baseUrl", None)
        openai.pop("apiKey", None)
        openai.pop("models", None)
    providers["openai-codex"] = {
        "api": "openai-completions",
        "apiKey": openai_ref,
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
            {
                "id": "gpt-5.3-codex-spark",
                "name": "GPT-5.3 Codex Spark via ccnode",
                "reasoning": True,
                "input": ["text", "image"],
                "contextWindow": 196000,
                "maxTokens": 32768,
            },
        ],
    }
    providers.pop("ollama", None)
    defaults = data.setdefault("agents", {}).setdefault("defaults", {}).setdefault("model", {})
    defaults["primary"] = "openai-codex/gpt-5.6-sol"
    defaults["fallbacks"] = []
    configured_models = data.setdefault("agents", {}).setdefault("defaults", {}).setdefault("models", {})
    configured_models.setdefault("openai-codex/gpt-5.6-sol", {})
    configured_models.setdefault("openai-codex/gpt-5.5", {})
    configured_models.setdefault("openai-codex/gpt-5.4", {})
    configured_models.setdefault("openai-codex/gpt-5.3-codex-spark", {})
    for stale_model in ("ollama/qwen3:14b", "ollama/qwen2.5:14b-instruct", "openai/gpt-5.5"):
        configured_models.pop(stale_model, None)
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
        "type": "api_key",
        "keyRef": openai_ref,
        "displayName": "ccnode gpt-5.6-sol",
        "copyToAgents": True,
    }
    profiles["openai-codex:default"] = {
        "provider": "openai-codex",
        "type": "api_key",
        "keyRef": openai_ref,
        "displayName": "ccnode gpt-5.6-sol",
        "copyToAgents": True,
    }
    profiles.pop("ollama:default", None)
    order = data.setdefault("order", {})
    order["openai"] = [item for item in order.get("openai", []) if item != "openai:ccnode-codex"]
    if "ollama" in order:
        order["ollama"] = [item for item in order.get("ollama", []) if item != "ollama:default"]
    last_good = data.setdefault("lastGood", {})
    if last_good.get("openai") == "openai:ccnode-codex":
        last_good.pop("openai", None)
    if last_good.get("ollama") == "ollama:default":
        last_good.pop("ollama", None)
    if write_json_if_changed(path, data):
        print(f"[model-auth-profile-guard] updated profile {path}")
print("[model-auth-profile-guard] ok")
PY

openai_tmp="$(mktemp /tmp/openclaw-codex-key.XXXXXX)"
chmod 600 "$openai_tmp"
trap 'rm -f "$openai_tmp"' EXIT
python3 - "$openai_tmp" <<'PY'
import json
import sys
from pathlib import Path

credential_path = Path("/run/credentials/openclaw.service/openclaw-secrets.json")
data = json.loads(credential_path.read_text(encoding="utf-8"))
Path(sys.argv[1]).write_text(str(data["providers"]["openaiCodex"]["apiKey"]), encoding="utf-8")
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
  sync_auth_profile paste-token openai openai:ccnode-codex "$openai_tmp"
  sync_auth_profile paste-token openai-codex openai-codex:default "$openai_tmp"
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
