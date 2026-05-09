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
MARKER = "springmonkey gateway payload trace"

OLD = '''\thandlePayload(payload, resume) {
\t\tif (payload.s !== null && payload.s !== void 0) this.sequence = payload.s;
\t\tswitch (payload.op) {'''

NEW = '''\thandlePayload(payload, resume) {
\t\tif (payload?.op === 0 || payload?.op === 10 || payload?.op === 9) console.log("discord gateway trace: springmonkey gateway payload trace op=" + String(payload?.op) + " t=" + String(payload?.t) + " resume=" + String(resume));
\t\tif (payload.s !== null && payload.s !== void 0) this.sequence = payload.s;
\t\tswitch (payload.op) {'''

OLD_DISPATCH = '''\t\t\tcase GatewayOpcodes.Dispatch:
\t\t\t\tthis.handleDispatch(payload).catch((error) => {'''

NEW_DISPATCH = '''\t\t\tcase GatewayOpcodes.Dispatch:
\t\t\t\tconsole.log("discord gateway trace: dispatch case t=" + String(payload?.t));
\t\t\t\tthis.handleDispatch(payload).catch((error) => {'''


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return False
    if OLD not in text or OLD_DISPATCH not in text:
        raise SystemExit(f"gateway payload trace anchor not found in {path}")
    backup = path.with_suffix(path.suffix + f".bak-gateway-payload-trace-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(path, backup)
    text = text.replace(OLD, NEW, 1).replace(OLD_DISPATCH, NEW_DISPATCH, 1)
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
    print("PATCH_DISCORD_GATEWAY_PAYLOAD_TRACE_OK", "changed" if changed else "already")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
