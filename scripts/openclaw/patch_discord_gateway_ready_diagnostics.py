#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil


DIST_ROOTS = [
    Path("/var/lib/openclaw/.openclaw/plugin-runtime-deps/openclaw-2026.4.29-4eca5026e977/dist/extensions/discord"),
    Path("/usr/lib/node_modules/openclaw/dist/extensions/discord"),
]

TARGET = "provider-hTInySyN.js"
MARKER = "springmonkey gateway ready diagnostics"

OLD = '''\t\tcreateWebSocket(url) {
\t\t\tif (!url) throw new Error("Gateway URL is required");
\t\t\tconst wsFlowId = randomUUID();
\t\t\tconst socket = new (params.testing?.webSocketCtor ?? ws.default)(url, {
\t\t\t\thandshakeTimeout: DISCORD_GATEWAY_HANDSHAKE_TIMEOUT_MS,
\t\t\t\t...params.wsAgent ? { agent: params.wsAgent } : {}
\t\t\t});'''

NEW = '''\t\tcreateWebSocket(url) {
\t\t\tif (!url) throw new Error("Gateway URL is required");
\t\t\tconst wsFlowId = randomUUID();
\t\t\tparams.runtime.log?.("discord gateway diag: springmonkey gateway ready diagnostics createWebSocket url=" + String(url).replace(/token=[^&]+/g, "token=<redacted>"));
\t\t\tconst socket = new (params.testing?.webSocketCtor ?? ws.default)(url, {
\t\t\t\thandshakeTimeout: DISCORD_GATEWAY_HANDSHAKE_TIMEOUT_MS,
\t\t\t\t...params.wsAgent ? { agent: params.wsAgent } : {}
\t\t\t});
\t\t\tsocket.on?.("open", () => params.runtime.log?.("discord gateway diag: websocket open"));
\t\t\tsocket.on?.("close", (code, reason) => params.runtime.error?.("discord gateway diag: websocket close code=" + String(code) + " reason=" + String(reason || "")));
\t\t\tsocket.on?.("error", (error) => params.runtime.error?.("discord gateway diag: websocket error " + (error?.stack || error?.message || String(error))));
\t\t\tsocket.on?.("message", (data) => {
\t\t\t\ttry {
\t\t\t\t\tconst payload = JSON.parse(Buffer.isBuffer(data) ? data.toString("utf8") : String(data));
\t\t\t\t\tif (payload?.op === 10 || payload?.t === "READY" || payload?.op === 9) params.runtime.log?.("discord gateway diag: inbound op=" + String(payload?.op) + " t=" + String(payload?.t));
\t\t\t\t} catch {}
\t\t\t});'''


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return False
    if OLD not in text:
        raise SystemExit(f"gateway diagnostic anchor not found in {path}")
    backup = path.with_suffix(path.suffix + f".bak-gateway-diag-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(path, backup)
    path.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print(f"patched {path} backup={backup}")
    return True


def main() -> int:
    changed = False
    found = False
    for root in DIST_ROOTS:
        path = root / TARGET
        if not path.is_file():
            continue
        found = True
        changed = patch_file(path) or changed
    if not found:
        raise SystemExit("discord provider bundle not found")
    print("PATCH_DISCORD_GATEWAY_READY_DIAGNOSTICS_OK", "changed" if changed else "already")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
