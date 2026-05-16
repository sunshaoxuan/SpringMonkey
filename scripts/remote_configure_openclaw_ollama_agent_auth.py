#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from openclaw_ssh_password import load_openclaw_ssh_password, missing_password_hint


HOST = "ccnode.briconbric.com"
PORT = 8822
USER = "root"
DEFAULT_REPO = "/var/lib/openclaw/repos/SpringMonkey"
DEFAULT_BASE_URL = "http://ccnode.briconbric.com:22545"
DEFAULT_MODEL = "qwen3:14b"
PLACEHOLDER_KEY = "ccnode-ollama-local"


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

    repo = os.environ.get("SPRINGMONKEY_REPO_PATH", DEFAULT_REPO).strip() or DEFAULT_REPO
    base_url = os.environ.get("OPENCLAW_OLLAMA_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    model = os.environ.get("OPENCLAW_QWEN_FALLBACK_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    remote = f"""
set -e
cd "{repo}"
python - <<'PY'
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

base_url = {base_url!r}
model = {model!r}
key = {PLACEHOLDER_KEY!r}
config_path = Path('/var/lib/openclaw/.openclaw/openclaw.json')
agent_dirs = [
    Path('/var/lib/openclaw/.openclaw/agents/main/agent'),
    Path('/root/.openclaw/agents/main/agent'),
]

def backup(path: Path) -> None:
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
        shutil.copy2(path, path.with_suffix(path.suffix + f'.bak-{{stamp}}'))

def ensure_auth(agent_dir: Path) -> None:
    agent_dir.mkdir(parents=True, exist_ok=True)
    path = agent_dir / 'auth-profiles.json'
    data = {{"version": 1, "profiles": {{}}, "order": {{}}, "lastGood": {{}}}}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(loaded, dict):
                data.update(loaded)
        except Exception:
            pass
    data.setdefault('version', 1)
    profiles = data.setdefault('profiles', {{}})
    profiles['ollama:default'] = {{
        'provider': 'ollama',
        'type': 'api_key',
        'key': key,
        'displayName': 'ccnode ollama',
        'copyToAgents': True,
    }}
    order = data.setdefault('order', {{}})
    existing = [item for item in order.get('ollama', []) if item != 'ollama:default']
    order['ollama'] = ['ollama:default'] + existing
    data.setdefault('lastGood', {{}})['ollama'] = 'ollama:default'
    backup(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\\n', encoding='utf-8')
    path.chmod(0o600)

def ensure_config() -> None:
    data = json.loads(config_path.read_text(encoding='utf-8'))
    models = data.setdefault('models', {{}})
    providers = models.setdefault('providers', {{}})
    ollama = providers.setdefault('ollama', {{}})
    ollama['baseUrl'] = base_url
    ollama['apiKey'] = key
    ollama['api'] = 'ollama'
    known = ollama.setdefault('models', [])
    if not any(isinstance(item, dict) and item.get('id') == model for item in known):
        known.insert(0, {{
            'id': model,
            'name': model,
            'reasoning': False,
            'input': ['text'],
            'contextWindow': 32768,
            'maxTokens': 32768,
            'api': 'ollama',
            'cost': {{'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}},
        }})
    defaults = data.setdefault('agents', {{}}).setdefault('defaults', {{}})
    model_cfg = defaults.setdefault('model', {{}})
    if not str(model_cfg.get('primary') or '').strip():
        model_cfg['primary'] = f'ollama/{{model}}'
    fallbacks = model_cfg.setdefault('fallbacks', [])
    fallback_id = f'ollama/{{model}}'
    if fallback_id not in fallbacks and model_cfg.get('primary') != fallback_id:
        fallbacks.insert(0, fallback_id)
    defaults.setdefault('models', {{}}).setdefault(fallback_id, {{}})
    backup(config_path)
    config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\\n', encoding='utf-8')

ensure_config()
for agent_dir in agent_dirs:
    ensure_auth(agent_dir)
print('ollama_agent_auth_configured')
print(f'base_url={{base_url}} model={{model}} key_marker={{key}}')
PY
systemctl restart openclaw.service
sleep 2
systemctl is-active openclaw.service
openclaw --no-color agent --agent main --model "ollama/{model}" --message "只回答 ok" --timeout 60 --thinking off --json >/tmp/openclaw-ollama-auth-smoke.json
python - <<'PY'
from pathlib import Path
text = Path('/tmp/openclaw-ollama-auth-smoke.json').read_text(encoding='utf-8', errors='replace')
print(text[-1000:])
PY
"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=password, timeout=20)
    try:
        stdin, stdout, stderr = client.exec_command(remote, timeout=180)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
    finally:
        client.close()
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
