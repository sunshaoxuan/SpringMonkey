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
READY_CONFIRM = 'params.runtime.log?.(`discord gateway READY confirmed for account ${params.accountId}`);'


DIAG_BLOCK = '''\t\t\tparams.runtime.log?.("discord gateway diag: springmonkey gateway ready diagnostics createWebSocket url=" + String(url).replace(/token=[^&]+/g, "token=<redacted>"));
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

DIAG_ORIGINAL = '''\t\t\tconst socket = new (params.testing?.webSocketCtor ?? ws.default)(url, {
\t\t\t\thandshakeTimeout: DISCORD_GATEWAY_HANDSHAKE_TIMEOUT_MS,
\t\t\t\t...params.wsAgent ? { agent: params.wsAgent } : {}
\t\t\t});'''

TRACE_LINES = [
    '\t\tif (payload?.op === 0 || payload?.op === 10 || payload?.op === 9) console.log("discord gateway trace: springmonkey gateway payload trace op=" + String(payload?.op) + " t=" + String(payload?.t) + " resume=" + String(resume));\n',
    '\t\t\t\tconsole.log("discord gateway trace: dispatch case t=" + String(payload?.t));\n',
    '\t\tif (payload.t === "READY") console.log("discord gateway trace: handleDispatch READY entered enum=" + String(GatewayDispatchEvents.Ready));\n',
    '\t\t\tconsole.log("discord gateway trace: springmonkey gateway ready state patch v2 READY handled isConnected=" + String(this.isConnected));\n',
]

WAIT_BLOCK = '''\t\tawait waitForGatewayReady({
\t\t\tgateway,
\t\t\tabortSignal: params.abortSignal,
\t\t\tbeforePoll: drainPendingGatewayErrors,
\t\t\tpushStatus,
\t\t\truntime: params.runtime,
\t\t\tbeforeRestart: statusObserver.clearReadyWatch
\t\t});
\t\tif (drainPendingGatewayErrors() === "stop") return;'''

WAIT_BLOCK_NEW = '''\t\tawait waitForGatewayReady({
\t\t\tgateway,
\t\t\tabortSignal: params.abortSignal,
\t\t\tbeforePoll: drainPendingGatewayErrors,
\t\t\tpushStatus,
\t\t\truntime: params.runtime,
\t\t\tbeforeRestart: statusObserver.clearReadyWatch
\t\t});
\t\tparams.runtime.log?.(`discord gateway READY confirmed for account ${params.accountId}`);
\t\tif (drainPendingGatewayErrors() === "stop") return;'''


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    if DIAG_BLOCK in text:
        text = text.replace(DIAG_BLOCK, DIAG_ORIGINAL, 1)
    for line in TRACE_LINES:
        text = text.replace(line, "")
    if READY_CONFIRM not in text:
        if WAIT_BLOCK not in text:
            raise SystemExit(f"READY confirmation anchor not found in {path}")
        text = text.replace(WAIT_BLOCK, WAIT_BLOCK_NEW, 1)
    if text == original:
        return False
    backup = path.with_suffix(path.suffix + f".bak-gateway-ready-final-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(path, backup)
    path.write_text(text, encoding="utf-8")
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
    print("PATCH_DISCORD_GATEWAY_READY_FINAL_OK", "changed" if changed else "already")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
