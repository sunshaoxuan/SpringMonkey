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
MARKER = "springmonkey fast READY state sync"

OLD = '''\t\t\tconst emitTransportActivity = () => {
\t\t\t\tif (this.ws !== socket) return;
\t\t\t\tthis.emitter.emit(DISCORD_GATEWAY_TRANSPORT_ACTIVITY_EVENT, { at: Date.now() });
\t\t\t};'''

NEW = '''\t\t\tconst emitTransportActivity = () => {
\t\t\t\tif (this.ws !== socket) return;
\t\t\t\tthis.emitter.emit(DISCORD_GATEWAY_TRANSPORT_ACTIVITY_EVENT, { at: Date.now() });
\t\t\t};
\t\t\tsocket.on?.("message", (data) => {
\t\t\t\tif (this.ws !== socket) return;
\t\t\t\ttry {
\t\t\t\t\tconst payload = JSON.parse(Buffer.isBuffer(data) ? data.toString("utf8") : String(data));
\t\t\t\t\tif (payload?.t === "READY") {
\t\t\t\t\t\tthis.isConnected = true;
\t\t\t\t\t\tthis.reconnectAttempts = 0;
\t\t\t\t\t\tthis.emitter.emit("debug", "springmonkey fast READY state sync");
\t\t\t\t\t}
\t\t\t\t} catch {}
\t\t\t});'''


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return False
    if OLD not in text:
        raise SystemExit(f"gateway fast ready state anchor not found in {path}")
    backup = path.with_suffix(path.suffix + f".bak-gateway-ready-fast-state-{datetime.now().strftime('%Y%m%d%H%M%S')}")
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
    print("PATCH_DISCORD_GATEWAY_READY_FAST_STATE_OK", "changed" if changed else "already")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
