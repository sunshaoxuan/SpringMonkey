#!/usr/bin/env python3
"""SSH 到汤猴宿主机，安装 memory-lancedb 启动级自愈守护。"""
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
LOCAL_PATCH = _SCRIPTS / "openclaw" / "patch_memory_lancedb_raw_embeddings_current.py"
REMOTE_PATCH = "/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw/patch_memory_lancedb_raw_embeddings_current.py"
LOCAL_AUTOCAPTURE_PATCH = _SCRIPTS / "openclaw" / "patch_memory_lancedb_autocapture_current.py"
REMOTE_AUTOCAPTURE_PATCH = "/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw/patch_memory_lancedb_autocapture_current.py"

REMOTE = r"""
set -e
install -d -m 755 /usr/local/lib/openclaw
install -d -m 755 /etc/systemd/system/openclaw.service.d
cat >/usr/local/lib/openclaw/ensure_memory_lancedb_guard.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
export HOME=/var/lib/openclaw
REPO=/var/lib/openclaw/repos/SpringMonkey
PATCH="${REPO}/scripts/openclaw/patch_memory_lancedb_raw_embeddings_current.py"
AUTOCAPTURE_PATCH="${REPO}/scripts/openclaw/patch_memory_lancedb_autocapture_current.py"
PLUGIN="/usr/lib/node_modules/openclaw/dist/extensions/memory-lancedb/index.js"
if [ ! -f "$PATCH" ]; then
  echo "[memory-guard] missing patch script: $PATCH" >&2
  exit 1
fi
if [ ! -f "$AUTOCAPTURE_PATCH" ]; then
  echo "[memory-guard] missing patch script: $AUTOCAPTURE_PATCH" >&2
  exit 1
fi
python3 "$PATCH" >/tmp/memory-lancedb-guard-patch.log 2>&1 || {
  cat /tmp/memory-lancedb-guard-patch.log >&2 || true
  exit 1
}
python3 "$AUTOCAPTURE_PATCH" >/tmp/memory-lancedb-guard-autocapture.log 2>&1 || {
  cat /tmp/memory-lancedb-guard-autocapture.log >&2 || true
  exit 1
}
python3 - <<'PY'
from pathlib import Path
plugin = Path("/usr/lib/node_modules/openclaw/dist/extensions/memory-lancedb/index.js")
text = plugin.read_text(encoding="utf-8")
required = [
    "const response = await fetch(`${baseUrl}/embeddings`, {",
    "Embeddings dimension mismatch: expected ${expectedDims}, got ${vector.length}",
    "function stripConversationMetadata(text) {",
    "remember|记住|记一下|请记住|别忘了",
    "const normalizedTexts = texts.map((text) => stripConversationMetadata(text)).filter(Boolean);",
]
missing = [item for item in required if item not in text]
if missing:
    raise SystemExit(f"[memory-guard] patched plugin verification failed: missing {missing}")
print("[memory-guard] patched plugin verification ok")
PY
EOF
chmod 755 /usr/local/lib/openclaw/ensure_memory_lancedb_guard.sh

cat >/usr/local/lib/openclaw/check_memory_lancedb_dims.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json
import urllib.request

url = "http://ccnode.briconbric.com:22545/v1/embeddings"
payload = json.dumps({"model": "bge-m3:latest", "input": "memory lancedb health check"}).encode()
req = urllib.request.Request(
    url,
    data=payload,
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer ollama-local-placeholder",
    },
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read().decode("utf-8"))
vec = data["data"][0]["embedding"]
dims = len(vec)
if dims != 1024:
    raise SystemExit(f"[memory-guard] embedding dims mismatch: {dims}")
print(f"[memory-guard] embedding dims ok: {dims}")
PY
EOF
chmod 755 /usr/local/lib/openclaw/check_memory_lancedb_dims.sh

cat >/etc/systemd/system/openclaw.service.d/20-memory-lancedb-guard.conf <<'EOF'
[Service]
TimeoutStartSec=120
ExecStartPre=/usr/local/lib/openclaw/ensure_memory_lancedb_guard.sh
ExecStartPost=/usr/local/lib/openclaw/check_memory_lancedb_dims.sh
EOF

systemctl daemon-reload
systemctl restart openclaw.service
sleep 12
systemctl is-active openclaw.service
echo "=== drop-in ==="
systemctl cat openclaw.service | sed -n '/20-memory-lancedb-guard.conf/,+10p'
echo "=== patch verify ==="
/usr/local/lib/openclaw/ensure_memory_lancedb_guard.sh
echo "=== dims verify ==="
/usr/local/lib/openclaw/check_memory_lancedb_dims.sh
echo "=== recent logs ==="
journalctl -u openclaw.service -n 80 --no-pager | grep -E 'memory-guard|memory-lancedb|gateway] ready' || true
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
        print(
            "缺少 paramiko。请执行一次：\n"
            "  python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt\n"
            "说明：SpringMonkey/docs/ops/SSH_TOOLCHAIN.md",
            file=sys.stderr,
        )
        return 1

    if not LOCAL_PATCH.is_file():
        print(f"missing local patch script: {LOCAL_PATCH}", file=sys.stderr)
        return 1
    if not LOCAL_AUTOCAPTURE_PATCH.is_file():
        print(f"missing local patch script: {LOCAL_AUTOCAPTURE_PATCH}", file=sys.stderr)
        return 1
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        HOST,
        port=PORT,
        username=USER,
        password=pw,
        timeout=60,
        allow_agent=False,
        look_for_keys=False,
    )
    stdin, stdout, stderr = c.exec_command(REMOTE, get_pty=True, timeout=900)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    c.close()
    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
