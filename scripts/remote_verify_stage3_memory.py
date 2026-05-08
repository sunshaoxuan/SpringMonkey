#!/usr/bin/env python3
"""Read-only remote validation for stage-3 self-evolution memory closure."""
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
QUERY = os.environ.get("OPENCLAW_MEMORY_VERIFY_QUERY", "小红书 Costco Frutteto 投稿")

REMOTE = r"""
set -uo pipefail
cd "$SPRINGMONKEY_REPO_PATH" || exit 1
QUERY="${OPENCLAW_MEMORY_VERIFY_QUERY:-小红书 Costco Frutteto 投稿}"

echo "=== git ==="
git rev-parse --short HEAD
git status --short

echo "=== service ==="
systemctl is-active openclaw.service || true

echo "=== memory plugin ==="
openclaw plugins inspect memory-lancedb 2>&1 | sed -n '1,80p' || true

echo "=== ltm stats ==="
openclaw ltm stats 2>&1 | sed -n '1,80p' || true

echo "=== ltm search ==="
openclaw ltm search "$QUERY" --limit 5 2>&1 | sed -n '1,160p' || true

echo "=== direct lancedb xhs recall ==="
NODE_PATH=/var/lib/openclaw/.openclaw/npm/node_modules:/root/.openclaw/npm/node_modules node - <<'NODE'
const lancedb = require("@lancedb/lancedb");
(async () => {
  const db = await lancedb.connect("/var/lib/openclaw/.openclaw/memory/lancedb");
  const names = await db.tableNames();
  console.log("tables=" + names.join(","));
  if (!names.includes("memories")) return;
  const table = await db.openTable("memories");
  const rows = await table.query().select(["id", "text", "category", "createdAt"]).toArray();
  console.log("total=" + rows.length);
  const hits = rows.filter((row) => /小红书|小紅書|XHS|Costco|Frutteto|投稿/i.test(String(row.text || "")));
  console.log("xhs_hits=" + hits.length);
  for (const row of hits.slice(0, 5)) console.log(String(row.text || "").slice(0, 260));
})().catch((err) => { console.error(err && err.stack ? err.stack : String(err)); process.exit(1); });
NODE

echo "=== memory curator dry-run ==="
python scripts/openclaw/memory_curator_tool.py --topic xhs --dry-run --limit 5 || true

echo "=== router clean safety ==="
python - <<'PY'
import sys
sys.path.insert(0, "scripts/openclaw")
import intent_tool_router as router
tool = {"args_schema": {"mode": "memory_curator", "topic": "xhs", "forget_marked": False, "limit": 25}}
print(router.extract_args(tool, "清理小红书长记忆噪声", "2026-05-08T00:00:00+09:00"))
print(router.extract_args(tool, "确认清理小红书长记忆噪声", "2026-05-08T00:00:00+09:00"))
PY

echo "=== self evolution status ==="
python scripts/openclaw/self_evolution_status.py --limit 5 || true

echo "=== embedding endpoint evidence ==="
python - <<'PY'
import json
import urllib.request
from pathlib import Path
cfg = json.loads(Path("/root/.openclaw/openclaw.json").read_text())
emb = cfg.get("plugins", {}).get("entries", {}).get("memory-lancedb", {}).get("config", {}).get("embedding", {})
print(json.dumps(emb, ensure_ascii=False, sort_keys=True))
base = str(emb.get("baseUrl") or "").rstrip("/")
model = str(emb.get("model") or "bge-m3:latest")
if base:
    for path in ["/api/tags", "/api/embed", "/v1/embeddings"]:
        url = base + path if not base.endswith("/v1") or path != "/v1/embeddings" else base + "/embeddings"
        try:
            data = None
            if path in {"/api/embed", "/v1/embeddings"}:
                payload = {"model": model, "input": "小红书 Costco Frutteto 投稿"}
                req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Authorization": "Bearer ollama-local"}, method="POST")
            else:
                req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = resp.read(300).decode("utf-8", errors="replace")
            print(f"{url}: ok {body[:180]}")
        except Exception as exc:
            print(f"{url}: {type(exc).__name__}: {exc}")
PY

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
    command = "\n".join(
        [
            f"export SPRINGMONKEY_REPO_PATH={REPO!r}",
            f"export OPENCLAW_MEMORY_VERIFY_QUERY={QUERY!r}",
            REMOTE.strip(),
        ]
    )
    _, stdout, stderr = client.exec_command(command, get_pty=True, timeout=600)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
    if err.strip():
        sys.stderr.buffer.write(err.encode("utf-8", errors="replace"))
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
