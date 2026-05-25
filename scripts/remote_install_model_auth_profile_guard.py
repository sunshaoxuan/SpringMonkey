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
sleep "${OPENCLAW_AUTH_PROFILE_GUARD_DELAY:-4}"
python3 - <<'PY'
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

secret_path = Path("/etc/openclaw/secrets/news_codex_api_key")
secret = secret_path.read_text(encoding="utf-8").strip() if secret_path.is_file() else ""
if not secret:
    raise SystemExit("[model-auth-profile-guard] missing /etc/openclaw/secrets/news_codex_api_key")

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
    rendered = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old == rendered:
        return False
    backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    path.chmod(0o600)
    return True


for path in config_paths:
    if not path.exists():
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    providers = data.setdefault("models", {}).setdefault("providers", {})
    openai = providers.setdefault("openai", {})
    openai["baseUrl"] = "http://ccnode.briconbric.com:49530/v1"
    openai["apiKey"] = secret
    models = openai.setdefault("models", [])
    if not any(isinstance(item, dict) and item.get("id") == "gpt-5.5" for item in models):
        models.insert(0, {"id": "gpt-5.5", "api": "openai-completions", "input": ["text"]})
    defaults = data.setdefault("agents", {}).setdefault("defaults", {}).setdefault("model", {})
    defaults["primary"] = "openai/gpt-5.5"
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
        "type": "api_key",
        "key": secret,
        "displayName": "ccnode gpt-5.5",
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
    order["openai"] = ["openai:ccnode-codex"] + [item for item in order.get("openai", []) if item != "openai:ccnode-codex"]
    order["ollama"] = ["ollama:default"] + [item for item in order.get("ollama", []) if item != "ollama:default"]
    last_good = data.setdefault("lastGood", {})
    last_good["openai"] = "openai:ccnode-codex"
    last_good["ollama"] = "ollama:default"
    if write_json_if_changed(path, data):
        print(f"[model-auth-profile-guard] updated profile {path}")
print("[model-auth-profile-guard] ok")
PY
EOF
chmod 755 /usr/local/lib/openclaw/ensure_model_auth_profiles.sh

cat >/etc/systemd/system/openclaw.service.d/35-model-auth-profile-guard.conf <<'EOF'
[Service]
ExecStartPost=/usr/local/lib/openclaw/ensure_model_auth_profiles.sh
EOF

systemctl daemon-reload
OPENCLAW_AUTH_PROFILE_GUARD_DELAY=0 /usr/local/lib/openclaw/ensure_model_auth_profiles.sh
systemctl restart openclaw.service
sleep 8
systemctl is-active openclaw.service
OPENCLAW_AUTH_PROFILE_GUARD_DELAY=0 /usr/local/lib/openclaw/ensure_model_auth_profiles.sh
echo "=== drop-in ==="
systemctl cat openclaw.service | sed -n '/35-model-auth-profile-guard.conf/,+5p'
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
