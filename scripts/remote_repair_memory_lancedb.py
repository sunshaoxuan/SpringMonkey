#!/usr/bin/env python3
"""SSH 到汤猴宿主机，修复 memory-lancedb 的 embedding 路径并验证。"""
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
USER = "root"

REMOTE = r"""
set -euo pipefail

python3 <<'PY'
from pathlib import Path
import shutil
from datetime import datetime

plugin = Path("/usr/lib/node_modules/openclaw/dist/extensions/memory-lancedb/index.js")
old = '''var Embeddings = class {
\tconstructor(apiKey, model, baseUrl, dimensions) {
\t\tthis.model = model;
\t\tthis.dimensions = dimensions;
\t\tthis.client = new OpenAI({
\t\t\tapiKey,
\t\t\tbaseURL: baseUrl
\t\t});
\t}
\tasync embed(text) {
\t\tconst params = {
\t\t\tmodel: this.model,
\t\t\tinput: text
\t\t};
\t\tif (this.dimensions) params.dimensions = this.dimensions;
\t\tensureGlobalUndiciEnvProxyDispatcher();
\t\treturn (await this.client.embeddings.create(params)).data[0].embedding;
\t}
};
'''
new = '''var Embeddings = class {
\tconstructor(apiKey, model, baseUrl, dimensions) {
\t\tthis.model = model;
\t\tthis.dimensions = dimensions;
\t\tthis.apiKey = apiKey;
\t\tthis.baseUrl = baseUrl;
\t\tthis.client = new OpenAI({
\t\t\tapiKey,
\t\t\tbaseURL: baseUrl
\t\t});
\t}
\tasync embed(text) {
\t\tconst baseUrl = typeof this.baseUrl === "string" && this.baseUrl.trim() ? this.baseUrl.replace(/\\/$/, "") : "";
\t\tconst expectedDims = typeof this.dimensions === "number" ? this.dimensions : void 0;
\t\tif (baseUrl) {
\t\t\tensureGlobalUndiciEnvProxyDispatcher();
\t\t\tconst response = await fetch(`${baseUrl}/embeddings`, {
\t\t\t\tmethod: "POST",
\t\t\t\theaders: {
\t\t\t\t\t"Content-Type": "application/json",
\t\t\t\t\tAuthorization: `Bearer ${this.apiKey}`
\t\t\t\t},
\t\t\t\tbody: JSON.stringify({
\t\t\t\t\tmodel: this.model,
\t\t\t\t\tinput: text
\t\t\t\t})
\t\t\t});
\t\t\tif (!response.ok) throw new Error(`Embeddings request failed (${response.status} ${response.statusText})`);
\t\t\tconst payload = await response.json();
\t\t\tconst embedding = payload?.data?.[0]?.embedding;
\t\t\tif (!Array.isArray(embedding) || embedding.length === 0) throw new Error("Embeddings response missing numeric vector");
\t\t\tconst vector = embedding.map((value) => Number(value));
\t\t\tif (vector.some((value) => !Number.isFinite(value))) throw new Error("Embeddings response contains non-numeric values");
\t\t\tif (expectedDims && vector.length !== expectedDims) throw new Error(`Embeddings dimension mismatch: expected ${expectedDims}, got ${vector.length}`);
\t\t\treturn vector;
\t\t}
\t\tconst params = {
\t\t\tmodel: this.model,
\t\t\tinput: text
\t\t};
\t\tif (this.dimensions) params.dimensions = this.dimensions;
\t\tensureGlobalUndiciEnvProxyDispatcher();
\t\tconst embedding = (await this.client.embeddings.create(params)).data[0].embedding;
\t\tif (expectedDims && Array.isArray(embedding) && embedding.length !== expectedDims) throw new Error(`Embeddings dimension mismatch: expected ${expectedDims}, got ${embedding.length}`);
\t\treturn embedding;
\t}
};
'''
text = plugin.read_text(encoding="utf-8")
if new not in text:
    if old not in text:
        raise SystemExit("expected Embeddings block not found; plugin layout changed")
    backup = plugin.with_name(f"{plugin.name}.bak-memory-raw-embeddings-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(plugin, backup)
    plugin.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"PATCHED {backup}")
else:
    print("PATCHED already")
PY

python3 /var/lib/openclaw/repos/SpringMonkey/scripts/openclaw/patch_memory_lancedb_autocapture_current.py

python3 <<'PY'
import json, shutil
from datetime import datetime
from pathlib import Path
p = Path("/var/lib/openclaw/.openclaw/openclaw.json")
ts = datetime.now().strftime("%Y%m%d-%H%M%S")
bak = p.with_name(f"openclaw.json.bak-memory-lancedb-repair-{ts}")
shutil.copy2(p, bak)
d = json.loads(p.read_text(encoding="utf-8"))
entries = d.setdefault("plugins", {}).setdefault("entries", {})
mem = entries.setdefault("memory-lancedb", {"enabled": True, "config": {}})
cfg = mem.setdefault("config", {})
emb = cfg.setdefault("embedding", {})
emb["apiKey"] = "ollama-local-placeholder"
emb["model"] = "bge-m3:latest"
emb["baseUrl"] = "http://ccnode.briconbric.com:22545/v1"
emb["dimensions"] = 1024
cfg["dbPath"] = "/var/lib/openclaw/.openclaw/memory/lancedb"
cfg["autoCapture"] = True
cfg["autoRecall"] = True
cfg["captureMaxChars"] = 2000
d.setdefault("plugins", {}).setdefault("slots", {})["memory"] = "memory-lancedb"
p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"CONFIG {bak}")
PY

systemctl restart openclaw.service
sleep 10
systemctl is-active openclaw.service

python3 <<'PY'
import json, urllib.request
body = {"model": "bge-m3:latest", "input": "memory repair verification"}
req = urllib.request.Request(
    "http://ccnode.briconbric.com:22545/v1/embeddings",
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json", "Authorization": "Bearer ollama-local-placeholder"},
)
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read().decode("utf-8"))
print("EMBED_DIMS", len(data["data"][0]["embedding"]))
PY

sudo -u openclaw env HOME=/var/lib/openclaw bash -lc 'timeout 60 openclaw agent --channel line -m "请用一句话回答：邮箱配置应写入什么文件并推送什么。" >/tmp/memory-repair-agent.txt 2>&1 || true; cat /tmp/memory-repair-agent.txt | sed -n "1,200p"'
echo ---
journalctl -u openclaw.service -n 120 --no-pager | grep -i "memory-lancedb" | tail -n 40 || true
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
            "  python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt",
            file=sys.stderr,
        )
        return 1
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=pw, timeout=60, allow_agent=False, look_for_keys=False)
    _, so, se = c.exec_command(REMOTE.strip(), get_pty=True)
    out = so.read().decode("utf-8", errors="replace")
    err = se.read().decode("utf-8", errors="replace")
    c.close()
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
    if err.strip():
        sys.stderr.buffer.write(err.encode("utf-8", errors="replace"))
    return 0 if "DONE" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
