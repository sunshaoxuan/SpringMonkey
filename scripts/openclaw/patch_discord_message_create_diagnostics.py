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
MARKER = "springmonkey message create diagnostics"

OLD = '''\tasync handle(data, client) {
\t\tthis.onEvent?.();
\t\tPromise.resolve().then(() => this.handler(data, client)).catch((err) => {'''

NEW = '''\tasync handle(data, client) {
\t\tthis.onEvent?.();
\t\ttry {
\t\t\tconst authorId = data?.author?.id ?? data?.author_id ?? data?.member?.user?.id ?? "";
\t\t\tconst channelId = data?.channel_id ?? data?.channelId ?? "";
\t\t\tconst guildId = data?.guild_id ?? data?.guildId ?? "";
\t\t\tthis.logger?.log?.("discord message diag: springmonkey message create diagnostics author=" + String(authorId) + " channel=" + String(channelId) + " guild=" + String(guildId));
\t\t} catch {}
\t\tPromise.resolve().then(() => this.handler(data, client)).catch((err) => {'''


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return False
    if OLD not in text:
        raise SystemExit(f"message create diagnostic anchor not found in {path}")
    backup = path.with_suffix(path.suffix + f".bak-message-create-diag-{datetime.now().strftime('%Y%m%d%H%M%S')}")
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
    print("PATCH_DISCORD_MESSAGE_CREATE_DIAGNOSTICS_OK", "changed" if changed else "already")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
