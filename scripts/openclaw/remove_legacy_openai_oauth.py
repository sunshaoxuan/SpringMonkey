#!/usr/bin/env python3
"""Idempotently remove the legacy OpenAI OAuth profile from one agent store."""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

TARGET_PROFILE = "openai:default"
DEFAULT_DB = Path("/root/.openclaw/agents/main/agent/openclaw-agent.sqlite")
DEFAULT_CONFIGS = (Path("/root/.openclaw/openclaw.json"), Path("/var/lib/openclaw/.openclaw/openclaw.json"))


def remove_from_config(path: Path, dry_run: bool) -> bool:
    if not path.is_file():
        return False
    config = json.loads(path.read_text(encoding="utf-8"))
    auth = config.get("auth")
    if not isinstance(auth, dict):
        return False
    changed = False
    profiles = auth.get("profiles")
    if isinstance(profiles, dict) and TARGET_PROFILE in profiles:
        del profiles[TARGET_PROFILE]
        changed = True
    order = auth.get("order")
    if isinstance(order, dict) and isinstance(order.get("openai"), list):
        retained = [item for item in order["openai"] if item != TARGET_PROFILE]
        if retained != order["openai"]:
            changed = True
            if retained:
                order["openai"] = retained
            else:
                del order["openai"]
    if changed and not dry_run:
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def remove_from_store(db_path: Path, dry_run: bool) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT store_json FROM auth_profile_store WHERE store_key = 'primary'").fetchone()
        if row is None:
            return False
        store: dict[str, Any] = json.loads(row[0])
        profiles = store.get("profiles")
        if not isinstance(profiles, dict) or TARGET_PROFILE not in profiles:
            return False
        profile = profiles[TARGET_PROFILE]
        if not isinstance(profile, dict) or profile.get("type") != "oauth":
            raise RuntimeError(f"refusing to remove non-OAuth profile: {TARGET_PROFILE}")
        del profiles[TARGET_PROFILE]
        if not dry_run:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE auth_profile_store SET store_json = ?, updated_at = ? WHERE store_key = 'primary'", (json.dumps(store, separators=(",", ":")), int(time.time() * 1000)))
            conn.commit()
        return True


def migrate(db_path: Path, config_paths: tuple[Path, ...], dry_run: bool) -> dict[str, bool]:
    return {"auth_store": remove_from_store(db_path, dry_run), **{str(path): remove_from_config(path, dry_run) for path in config_paths}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--config", type=Path, action="append")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    configs = tuple(args.config) if args.config else DEFAULT_CONFIGS
    result = migrate(args.db, configs, dry_run=not args.apply)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
