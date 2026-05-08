#!/usr/bin/env python3
"""SSH to OpenClaw host, repair memory-lancedb config, and validate recall."""
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
REPO = os.environ.get("SPRINGMONKEY_REPO_PATH", "/var/lib/openclaw/repos/SpringMonkey")

REMOTE = r"""
set -euo pipefail
REPO="${SPRINGMONKEY_REPO_PATH:-/var/lib/openclaw/repos/SpringMonkey}"
OPENCLAW_CONFIG="${OPENCLAW_CONFIG:-/root/.openclaw/openclaw.json}"
MEMORY_MODEL="${OPENCLAW_MEMORY_EMBED_MODEL:-bge-m3:latest}"
MEMORY_DIMS="${OPENCLAW_MEMORY_EMBED_DIMS:-1024}"
QUERY="${OPENCLAW_MEMORY_VERIFY_QUERY:-小红书 Costco Frutteto 投稿}"

cd "$REPO"

echo "=== patch loaded memory-lancedb plugin ==="
python3 scripts/openclaw/patch_memory_lancedb_raw_embeddings_current.py || true
python3 scripts/openclaw/patch_memory_lancedb_autocapture_current.py || true
python3 scripts/openclaw/patch_memory_lancedb_text_fallback_current.py

echo "=== repair OpenClaw config schema and memory config ==="
python3 <<'PY'
import json
import os
import shutil
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

config_path = Path(os.environ.get("OPENCLAW_CONFIG", "/root/.openclaw/openclaw.json"))
model = os.environ.get("OPENCLAW_MEMORY_EMBED_MODEL", "bge-m3:latest")
dims = int(os.environ.get("OPENCLAW_MEMORY_EMBED_DIMS", "1024"))
configured = os.environ.get("OPENCLAW_MEMORY_OLLAMA_BASE_URL", "").strip()

def probe_ollama(base: str) -> tuple[bool, str]:
    base = base.rstrip("/")
    payload = json.dumps({"model": model, "input": "memory lancedb health check"}).encode("utf-8")
    for path in ("/api/embed", "/api/embeddings"):
        try:
            req = urllib.request.Request(
                base + path,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            vec = data.get("embeddings", [[None]])[0] if "embeddings" in data else data.get("embedding")
            if isinstance(vec, list) and len(vec) == dims:
                return True, f"{base} {path} dims={len(vec)}"
            return False, f"{base} {path} wrong dims={len(vec) if isinstance(vec, list) else 'none'}"
        except Exception as exc:
            last = f"{base} {path} {type(exc).__name__}: {exc}"
    return False, last

def probe_openai(base: str) -> tuple[bool, str]:
    base = base.rstrip("/")
    url = base if base.endswith("/v1") else base + "/v1"
    payload = json.dumps({"model": model, "input": "memory lancedb health check"}).encode("utf-8")
    try:
        req = urllib.request.Request(
            url + "/embeddings",
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": "Bearer ollama-local"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        vec = data.get("data", [{}])[0].get("embedding")
        if isinstance(vec, list) and len(vec) == dims:
            return True, f"{url}/embeddings dims={len(vec)}"
        return False, f"{url}/embeddings wrong dims={len(vec) if isinstance(vec, list) else 'none'}"
    except Exception as exc:
        return False, f"{url}/embeddings {type(exc).__name__}: {exc}"

candidates = []
if configured:
    candidates.append(configured)
candidates.extend([
    "http://127.0.0.1:22545",
    "http://127.0.0.1:11434",
    "http://localhost:22545",
    "http://ccnode.briconbric.com:22545",
])
try:
    host_ip = socket.gethostbyname(socket.gethostname())
    candidates.append(f"http://{host_ip}:22545")
except Exception:
    pass
seen = []
for item in candidates:
    item = item.rstrip("/")
    if item and item not in seen:
        seen.append(item)

selected = None
probe_log = []
for base in seen:
    ok, msg = probe_ollama(base)
    probe_log.append(msg)
    if ok:
        selected = {"provider": "ollama", "baseUrl": base, "apiKey": "ollama-local"}
        break
    ok, msg = probe_openai(base)
    probe_log.append(msg)
    if ok:
        selected = {"provider": "openai", "baseUrl": base.rstrip("/") + "/v1", "apiKey": "ollama-local"}
        break

if selected is None:
    fallback = configured.rstrip("/") if configured else "http://ccnode.briconbric.com:22545"
    selected = {"provider": "ollama", "baseUrl": fallback, "apiKey": "ollama-local"}
    probe_log.append("no embedding endpoint currently reachable; text fallback remains enabled")

data = json.loads(config_path.read_text(encoding="utf-8"))
backup = config_path.with_suffix(config_path.suffix + ".memory-stage3-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".bak")
shutil.copy2(config_path, backup)

agents_defaults = data.get("agents", {}).get("defaults")
if isinstance(agents_defaults, dict):
    agents_defaults.pop("llm", None)

discord = data.setdefault("channels", {}).setdefault("discord", {})
if not isinstance(discord.get("streaming"), dict):
    discord["streaming"] = {"mode": "off"}
for guild in (discord.get("guilds") or {}).values():
    if isinstance(guild, dict):
        for channel in (guild.get("channels") or {}).values():
            if isinstance(channel, dict):
                channel.pop("allow", None)

entry = data.setdefault("plugins", {}).setdefault("entries", {}).setdefault("memory-lancedb", {})
entry["enabled"] = True
cfg = entry.setdefault("config", {})
emb = cfg.setdefault("embedding", {})
emb["provider"] = selected["provider"]
emb["model"] = model
emb["baseUrl"] = selected["baseUrl"]
emb["apiKey"] = selected["apiKey"]
emb["dimensions"] = dims
cfg["dbPath"] = "/var/lib/openclaw/.openclaw/memory/lancedb"
cfg["autoCapture"] = True
cfg["autoRecall"] = True
cfg["captureMaxChars"] = 2000
data.setdefault("plugins", {}).setdefault("slots", {})["memory"] = "memory-lancedb"

config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("CONFIG_BACKUP", backup)
print("MEMORY_EMBEDDING", json.dumps(emb, ensure_ascii=False, sort_keys=True))
print("PROBE_LOG")
for item in probe_log:
    print(" - " + item)
PY

echo "=== restart openclaw.service ==="
systemctl restart openclaw.service
sleep 3
systemctl is-active openclaw.service

echo "=== validate memory-lancedb ==="
openclaw plugins inspect memory-lancedb | sed -n '1,40p'
openclaw ltm stats
openclaw ltm search "$QUERY" --limit 5
python scripts/openclaw/memory_curator_tool.py --topic xhs --dry-run --limit 5
python scripts/openclaw/self_evolution_status.py --limit 5
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
        print("缺少 paramiko。请执行：python -m pip install -r scripts/requirements-ssh.txt", file=sys.stderr)
        return 1
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=pw, timeout=90, allow_agent=False, look_for_keys=False)
    command = "\n".join([f"export SPRINGMONKEY_REPO_PATH={REPO!r}", REMOTE.strip()])
    _, stdout, stderr = client.exec_command(command, get_pty=True, timeout=900)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
    if err.strip():
        sys.stderr.buffer.write(err.encode("utf-8", errors="replace"))
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
