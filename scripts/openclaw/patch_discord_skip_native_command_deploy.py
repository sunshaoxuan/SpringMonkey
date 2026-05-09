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

OLD = '''\t\tlogDiscordStartupPhase({
\t\t\truntime,
\t\t\taccountId: account.accountId,
\t\t\tphase: "deploy-commands:schedule",
\t\t\tstartAt: startupStartedAt,
\t\t\tgateway: lifecycleGateway,
\t\t\tdetails: `native=${nativeEnabled ? "on" : "off"} reconcile=on commandCount=${commands.length}`
\t\t});
\t\trunDiscordCommandDeployInBackground({
\t\t\tclient,
\t\t\truntime,
\t\t\tenabled: nativeEnabled,
\t\t\taccountId: account.accountId,
\t\t\tstartupStartedAt,
\t\t\tshouldLogVerbose: shouldLogVerboseForTesting ?? shouldLogVerbose,
\t\t\tisVerbose: isVerboseForTesting ?? isVerbose
\t\t});'''

NEW = '''\t\tlogDiscordStartupPhase({
\t\t\truntime,
\t\t\taccountId: account.accountId,
\t\t\tphase: "deploy-commands:skipped",
\t\t\tstartAt: startupStartedAt,
\t\t\tgateway: lifecycleGateway,
\t\t\tdetails: `native=${nativeEnabled ? "on" : "off"} reconcile=off reason=springmonkey_dm_first_startup_guard commandCount=${commands.length}`
\t\t});
\t\truntime.log?.(warn("discord: native slash command deploy skipped by SpringMonkey DM-first startup guard; existing slash commands remain active."));'''


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if NEW in text:
        return False
    if OLD not in text:
        raise SystemExit(f"native deploy anchor not found in {path}")
    backup = path.with_suffix(path.suffix + f".bak-skip-native-deploy-{datetime.now().strftime('%Y%m%d%H%M%S')}")
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
    print("PATCH_DISCORD_SKIP_NATIVE_COMMAND_DEPLOY_OK", "changed" if changed else "already")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
