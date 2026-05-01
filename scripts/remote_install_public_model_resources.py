#!/usr/bin/env python3
"""Install shared model resource env for OpenClaw host tasks."""
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

REMOTE = r"""
set -euo pipefail

ENV_FILE="/etc/openclaw/openclaw.env"
CODEX_BASE_URL="${OPENCLAW_PUBLIC_MODEL_BASE_URL:-${NEWS_CODEX_BASE_URL:-http://ccnode.briconbric.com:49530/v1}}"

install -d -m 755 /etc/openclaw
if getent group openclaw >/dev/null 2>&1; then
  install -m 640 -o root -g openclaw /dev/null "${ENV_FILE}.tmp"
else
  install -m 600 -o root -g root /dev/null "${ENV_FILE}.tmp"
fi

if [ -f "${ENV_FILE}" ]; then
  cp -a "${ENV_FILE}" "${ENV_FILE}.bak-public-model-$(date +%Y%m%d-%H%M%S)"
  cp -a "${ENV_FILE}" "${ENV_FILE}.tmp"
fi

python3 <<'PY'
import os
from pathlib import Path

path = Path("/etc/openclaw/openclaw.env")
base_url = os.environ.get("CODEX_BASE_URL", "http://ccnode.briconbric.com:49530/v1").strip()
key_aliases = [
    "NEWS_CODEX_API_KEY",
    "OPENCLAW_PUBLIC_MODEL_API_KEY",
    "CODEX_API_KEY",
    "OPENAI_CODEX_API_KEY",
]
base_aliases = [
    "NEWS_CODEX_BASE_URL",
    "OPENCLAW_PUBLIC_MODEL_BASE_URL",
]

lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
values: dict[str, str] = {}
order: list[str] = []
for raw in lines:
    stripped = raw.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        continue
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].strip()
    key, value = stripped.split("=", 1)
    key = key.strip()
    if not key:
        continue
    values[key] = value.strip().strip('"').strip("'")
    if key not in order:
        order.append(key)

for alias in base_aliases:
    values[alias] = base_url
    if alias not in order:
        order.append(alias)

shared_key = ""
for alias in key_aliases:
    env_value = os.environ.get(alias, "").strip()
    if env_value:
        shared_key = env_value
        break
for alias in key_aliases:
    if values.get(alias):
        shared_key = values[alias]
        break
if shared_key:
    for alias in key_aliases:
        values[alias] = shared_key
        if alias not in order:
            order.append(alias)

header = [
    "# OpenClaw shared public model resources.",
    "# Secrets live on the host only; Git stores variable names and endpoints, not keys.",
]
body = []
for key in order:
    if key in values:
        body.append(f"{key}={values[key]}")
path.write_text("\n".join(header + body).rstrip() + "\n", encoding="utf-8")
print("PUBLIC_MODEL_ENV_UPDATED")
print(f"NEWS_CODEX_BASE_URL={values.get('NEWS_CODEX_BASE_URL', '')}")
print(f"OPENCLAW_PUBLIC_MODEL_BASE_URL={values.get('OPENCLAW_PUBLIC_MODEL_BASE_URL', '')}")
print(f"NEWS_CODEX_API_KEY={'set' if values.get('NEWS_CODEX_API_KEY') else 'missing'}")
print(f"OPENCLAW_PUBLIC_MODEL_API_KEY={'set' if values.get('OPENCLAW_PUBLIC_MODEL_API_KEY') else 'missing'}")
PY

chmod 640 "${ENV_FILE}" || chmod 600 "${ENV_FILE}"

install -d -m 755 /etc/systemd/system/openclaw.service.d
cat >/etc/systemd/system/openclaw.service.d/10-shared-capabilities.conf <<'EOF'
[Service]
EnvironmentFile=-/etc/openclaw/openclaw.env
EOF

systemctl daemon-reload
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

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=password, timeout=60, allow_agent=False, look_for_keys=False)
    try:
        _, stdout, stderr = client.exec_command(REMOTE.strip(), get_pty=True, timeout=180)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
    finally:
        client.close()
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write(err)
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
