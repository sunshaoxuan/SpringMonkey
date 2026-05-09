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
MARKER = "springmonkey gateway ready state patch"

OLD = '''\t\tasync handleDispatch(payload) {
\t\t\tif (!this.client || !payload.t) return;
\t\t\tif (payload.t === GatewayDispatchEvents.Ready) {
\t\t\t\tconst ready = payload.d;
\t\t\t\tthis.sessionId = ready.session_id ?? null;
\t\t\t\tthis.resumeGatewayUrl = ready.resume_gateway_url ?? null;
\t\t\t\tthis.reconnectAttempts = 0;
\t\t\t\tthis.isConnected = true;
\t\t\t}'''

NEW = '''\t\tasync handleDispatch(payload) {
\t\t\tif (!this.client || !payload.t) return;
\t\t\tif (payload.t === GatewayDispatchEvents.Ready) {
\t\t\t\tconst ready = payload.d;
\t\t\t\tthis.sessionId = ready.session_id ?? null;
\t\t\t\tthis.resumeGatewayUrl = ready.resume_gateway_url ?? null;
\t\t\t\tthis.reconnectAttempts = 0;
\t\t\t\tthis.isConnected = true;
\t\t\t\tthis.emitter.emit("debug", "springmonkey gateway ready state patch: READY handled isConnected=true");
\t\t\t}'''


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return False
    if OLD not in text:
        raise SystemExit(f"gateway ready state anchor not found in {path}")
    backup = path.with_suffix(path.suffix + f".bak-gateway-ready-state-{datetime.now().strftime('%Y%m%d%H%M%S')}")
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
    print("PATCH_DISCORD_GATEWAY_READY_STATE_OK", "changed" if changed else "already")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
