#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_CONFIGS = (
    Path("/var/lib/openclaw/.openclaw/openclaw.json"),
    Path("/var/lib/openclaw/.openclaw/openclaw.json.last-good"),
)

LEGACY_DISCORD_PLUGIN_CANDIDATES = (
    Path("/var/lib/openclaw/.openclaw/plugin-runtime-deps/openclaw-2026.4.29-4eca5026e977/dist/extensions/discord"),
    Path("/var/lib/openclaw/.openclaw/plugin-runtime-deps/openclaw-2026.4.25-4eca5026e977/dist/extensions/discord"),
)
BUNDLED_DISCORD_PLUGIN = Path("/usr/lib/node_modules/openclaw/dist/extensions/discord")


@dataclass(frozen=True)
class RepairResult:
    path: Path
    changed: bool
    backup: Path | None
    actions: tuple[str, ...]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def first_existing_plugin_path(paths: tuple[Path, ...]) -> str | None:
    for path in paths:
        if (path / "index.js").is_file():
            return str(path)
    return None


def repair_config_data(data: dict[str, Any], *, discord_plugin_path: str | None = None) -> list[str]:
    actions: list[str] = []

    agents = data.get("agents")
    if isinstance(agents, dict):
        defaults = agents.get("defaults")
        if isinstance(defaults, dict) and "llm" in defaults:
            defaults.pop("llm", None)
            actions.append("removed legacy agents.defaults.llm")

    tools = data.get("tools")
    search = None
    if isinstance(tools, dict):
        web = tools.get("web")
        if isinstance(web, dict):
            search = web.get("search")
    if isinstance(search, dict) and search.get("provider") == "brave":
        search["enabled"] = False
        search.pop("provider", None)
        actions.append("disabled unavailable brave web_search provider")

    plugins = data.get("plugins")
    if isinstance(plugins, dict):
        slots = plugins.get("slots")
        if isinstance(slots, dict) and slots.get("memory") == "memory-lancedb":
            slots.pop("memory", None)
            if not slots:
                plugins.pop("slots", None)
            actions.append("cleared unavailable memory-lancedb plugin slot")

    channels = data.get("channels")
    discord = channels.get("discord") if isinstance(channels, dict) else None
    discord_enabled = isinstance(discord, dict) and discord.get("enabled") is not False
    if discord_enabled and discord_plugin_path and not BUNDLED_DISCORD_PLUGIN.exists():
        plugins = data.setdefault("plugins", {})
        if isinstance(plugins, dict):
            load = plugins.setdefault("load", {})
            if isinstance(load, dict):
                paths = load.setdefault("paths", [])
                if isinstance(paths, list) and discord_plugin_path not in paths:
                    paths.append(discord_plugin_path)
                    actions.append("added legacy discord plugin load path")

    return actions


def repair_config(path: Path, *, dry_run: bool = False, backup_suffix: str | None = None) -> RepairResult:
    if not path.exists():
        return RepairResult(path=path, changed=False, backup=None, actions=("missing",))

    data = load_json(path)
    actions = repair_config_data(data, discord_plugin_path=first_existing_plugin_path(LEGACY_DISCORD_PLUGIN_CANDIDATES))
    if not actions:
        return RepairResult(path=path, changed=False, backup=None, actions=())

    backup: Path | None = None
    if not dry_run:
        suffix = backup_suffix or datetime.now().strftime("%Y%m%d%H%M%S")
        backup = path.with_name(f"{path.name}.bak-gateway-config-repair-{suffix}")
        shutil.copy2(path, backup)
        dump_json(path, data)

    return RepairResult(path=path, changed=True, backup=backup, actions=tuple(actions))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Repair OpenClaw gateway config keys that block startup before channel routing can run."
    )
    parser.add_argument(
        "--config",
        action="append",
        type=Path,
        default=None,
        help="Config path to repair. Repeatable. Defaults to openclaw.json and openclaw.json.last-good.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup-suffix", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = tuple(args.config or DEFAULT_CONFIGS)
    any_changed = False
    for path in paths:
        result = repair_config(path, dry_run=args.dry_run, backup_suffix=args.backup_suffix)
        any_changed = any_changed or result.changed
        action_text = ",".join(result.actions) if result.actions else "no_change"
        backup_text = str(result.backup) if result.backup else ""
        print(f"{path}: changed={str(result.changed).lower()} actions={action_text} backup={backup_text}")
    print(f"openclaw_gateway_config_repair_ok changed={str(any_changed).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
