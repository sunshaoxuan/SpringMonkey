#!/usr/bin/env python3
"""Enable the live-validated Sub2API Qwen model as the durable fallback."""
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
MODEL = "hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S"
BASE_URL = "http://ccnode.briconbric.com:49530/v1"
INTENT_TIMEOUT_SECONDS = 180


REMOTE = r"""
set -euo pipefail

MODEL="__MODEL__"
BASE_URL="__BASE_URL__"
INTENT_TIMEOUT_SECONDS="__INTENT_TIMEOUT_SECONDS__"
ENV_FILE="/etc/openclaw/openclaw.env"
KEY_FILE="/etc/openclaw/secrets/news_codex_api_key"
GUARD="/usr/local/lib/openclaw/ensure_model_auth_profiles.sh"

if [ ! -x "$GUARD" ]; then
  echo "QWEN_FALLBACK_NOT_ENABLED missing_model_auth_profile_guard"
  exit 2
fi

if getent group openclaw >/dev/null 2>&1; then
  install -d -m 750 -o root -g openclaw /etc/openclaw/secrets
else
  install -d -m 700 -o root -g root /etc/openclaw/secrets
fi

python3 - "$KEY_FILE" <<'PY'
import json
import sys
from pathlib import Path

target = Path(sys.argv[1])
if not target.is_file() or not target.read_text(encoding="utf-8").strip():
    key = ""
    for path in [
        Path("/run/credentials/openclaw.service/openclaw-secrets.json"),
        Path("/etc/openclaw/openclaw-secrets.json"),
    ]:
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        node = data.get("providers", {}).get("openaiCodex")
        if isinstance(node, dict) and node.get("apiKey"):
            key = str(node["apiKey"])
            break
    if not key:
        print("QWEN_FALLBACK_NOT_ENABLED missing_codex_key")
        raise SystemExit(2)
    target.write_text(key + "\n", encoding="utf-8")
target.chmod(0o640)
print("QWEN_FALLBACK_KEY_FILE_READY")
PY

if getent group openclaw >/dev/null 2>&1; then
  chown root:openclaw "$KEY_FILE"
  chmod 640 "$KEY_FILE"
fi

python3 - "$MODEL" "$BASE_URL" "$INTENT_TIMEOUT_SECONDS" "$KEY_FILE" <<'PY'
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

model, base_url, timeout_raw, key_file = sys.argv[1:]
base_url = base_url.rstrip("/")
timeout = int(timeout_raw)
key = Path(key_file).read_text(encoding="utf-8").strip()
if not key:
    print("QWEN_FALLBACK_NOT_ENABLED empty_codex_key")
    raise SystemExit(2)

headers = {"Authorization": "Bearer " + key}
models_req = urllib.request.Request(base_url + "/models", headers=headers)
models_data = json.loads(urllib.request.urlopen(models_req, timeout=30).read().decode("utf-8", "replace"))
available = {str(item.get("id") or "") for item in models_data.get("data", []) if isinstance(item, dict)}
if model not in available:
    print(f"QWEN_FALLBACK_NOT_ENABLED model_not_visible={model}")
    raise SystemExit(2)

system = (
    "Return strict JSON only without markdown fences. Required keys: conversation_mode, domain, action, "
    "canonical_text, context_refs, parameters, safety, result_contract, tool_candidates, confidence, reason. "
    "Use conversation_mode=chat, domain=general, action=chat, safety=readonly."
)
payload = {
    "model": model,
    "messages": [{"role": "system", "content": system}, {"role": "user", "content": "你好"}],
    "temperature": 0,
}
request = urllib.request.Request(
    base_url + "/chat/completions",
    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    method="POST",
)
try:
    data = json.loads(urllib.request.urlopen(request, timeout=timeout).read().decode("utf-8", "replace"))
    text = str(data["choices"][0]["message"]["content"]).strip()
    frame = json.loads(text[text.find("{") : text.rfind("}") + 1])
except urllib.error.HTTPError as exc:
    detail = exc.read(500).decode("utf-8", "replace").replace("\n", " ")
    print(f"QWEN_FALLBACK_NOT_ENABLED http_{exc.code} {detail}")
    raise SystemExit(2)
except Exception as exc:
    print(f"QWEN_FALLBACK_NOT_ENABLED {type(exc).__name__}: {exc}")
    raise SystemExit(2)
required = {
    "conversation_mode", "domain", "action", "canonical_text", "context_refs", "parameters",
    "safety", "result_contract", "tool_candidates", "confidence", "reason",
}
if not required.issubset(frame) or frame.get("conversation_mode") != "chat":
    print(f"QWEN_FALLBACK_NOT_ENABLED invalid_intent_frame keys={sorted(frame)}")
    raise SystemExit(2)
print(f"QWEN_FALLBACK_SMOKE_OK model={model}")
PY

python3 - "$MODEL" "$BASE_URL" "$INTENT_TIMEOUT_SECONDS" "$ENV_FILE" "$KEY_FILE" <<'PY'
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sys

model, base_url, timeout_seconds, env_file, key_file = sys.argv[1:]
path = Path(env_file)
values = {}
order = []
if path.exists():
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
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
    "OPENCLAW_MODEL_FALLBACK_TIMEOUT_SECONDS": timeout_seconds,
    "OPENCLAW_INTENT_FALLBACK_BASE_URL": base_url,
    "OPENCLAW_INTENT_FALLBACK_MODELS": model,
    "OPENCLAW_INTENT_FALLBACK_API_KEY_FILE": key_file,
    "OPENCLAW_INTENT_FALLBACK_TIMEOUT_SECONDS": timeout_seconds,
    "NEWS_FALLBACK_MODEL": f"openai-codex/{model}",
}
for key, value in additions.items():
    values[key] = value
    if key not in order:
        order.append(key)
if path.exists():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, path.with_suffix(path.suffix + f".bak-qwen-fallback-{stamp}"))
rendered = "\n".join(f"{key}={values[key]}" for key in order).rstrip() + "\n"
temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
temporary.write_text(rendered, encoding="utf-8")
if path.exists():
    stat = path.stat()
    temporary.chmod(stat.st_mode & 0o777)
    os.chown(temporary, stat.st_uid, stat.st_gid)
else:
    temporary.chmod(0o640)
os.replace(temporary, path)
print(f"QWEN_FALLBACK_ENV_ENABLED model={model} base_url={base_url} timeout={timeout_seconds}")
PY

OPENCLAW_AUTH_PROFILE_GUARD_DELAY=0 \
OPENCLAW_MODEL_FALLBACK="$MODEL" \
OPENCLAW_MODEL_FALLBACK_BASE_URL="$BASE_URL" \
  "$GUARD"
systemctl daemon-reload
systemctl restart openclaw.service
sleep 35
systemctl is-active openclaw.service
python3 - "$MODEL" "$BASE_URL" "$INTENT_TIMEOUT_SECONDS" "$KEY_FILE" <<'PY'
import json
import sys
from pathlib import Path

model, base_url, timeout_seconds, key_file = sys.argv[1:]
expected = {
    "OPENCLAW_MODEL_FALLBACK_BASE_URL": base_url,
    "OPENCLAW_MODEL_FALLBACK": model,
    "OPENCLAW_MODEL_FALLBACK_TIMEOUT_SECONDS": timeout_seconds,
    "OPENCLAW_INTENT_FALLBACK_BASE_URL": base_url,
    "OPENCLAW_INTENT_FALLBACK_MODELS": model,
    "OPENCLAW_INTENT_FALLBACK_TIMEOUT_SECONDS": timeout_seconds,
}
values = {}
for raw in Path("/etc/openclaw/openclaw.env").read_text(encoding="utf-8").splitlines():
    if "=" not in raw or raw.lstrip().startswith("#"):
        continue
    key, value = raw.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")
for key, value in expected.items():
    if values.get(key) != value:
        raise SystemExit(f"fallback env mismatch: {key}")
if not Path(key_file).is_file() or not Path(key_file).read_text(encoding="utf-8").strip():
    raise SystemExit(f"fallback key file missing or empty: {key_file}")
checked = 0
for path in [Path("/var/lib/openclaw/.openclaw/openclaw.json"), Path("/root/.openclaw/openclaw.json")]:
    if not path.is_file():
        continue
    checked += 1
    data = json.loads(path.read_text(encoding="utf-8"))
    fallbacks = data.get("agents", {}).get("defaults", {}).get("model", {}).get("fallbacks", [])
    expected_model = f"openai-codex/{model}"
    if fallbacks != [expected_model]:
        raise SystemExit(f"fallback config mismatch: {path}: {fallbacks}")
if checked == 0:
    raise SystemExit("fallback config mismatch: no openclaw.json found")
print("QWEN_FALLBACK_CONFIG_OK")
PY
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
        print("paramiko is required for remote installation", file=sys.stderr)
        return 1

    remote = (
        REMOTE.replace("__MODEL__", MODEL)
        .replace("__BASE_URL__", BASE_URL)
        .replace("__INTENT_TIMEOUT_SECONDS__", str(INTENT_TIMEOUT_SECONDS))
    )
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=password, timeout=60, allow_agent=False, look_for_keys=False)
    try:
        _, stdout, stderr = client.exec_command(remote, get_pty=True, timeout=300)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
    finally:
        client.close()
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
    if err.strip():
        sys.stderr.buffer.write(err.encode("utf-8", errors="replace"))
    required = ("QWEN_FALLBACK_SMOKE_OK", "QWEN_FALLBACK_CONFIG_OK", "DONE")
    return 0 if rc == 0 and all(token in out for token in required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
