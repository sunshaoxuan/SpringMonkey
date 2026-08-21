from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from remove_legacy_openai_oauth import TARGET_PROFILE, migrate


def setup_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE auth_profile_store (store_key TEXT PRIMARY KEY, store_json TEXT NOT NULL, updated_at INTEGER NOT NULL)")
        conn.execute("INSERT INTO auth_profile_store VALUES (?, ?, ?)", ("primary", json.dumps({"version": 1, "profiles": {TARGET_PROFILE: {"type": "oauth", "access": "redacted"}, "openai:ccnode-codex": {"type": "api_key", "keyRef": {"source": "file"}}}}), 1))


def test_removes_only_legacy_oauth_and_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "agent.sqlite"
    setup_db(db)
    config = tmp_path / "openclaw.json"
    config.write_text(json.dumps({"auth": {"profiles": {TARGET_PROFILE: {"provider": "openai", "mode": "oauth"}}, "order": {"openai": [TARGET_PROFILE]}}}))
    assert all(migrate(db, (config,), dry_run=True).values())
    result = migrate(db, (config,), dry_run=False)
    assert all(result.values())
    with sqlite3.connect(db) as conn:
        store = json.loads(conn.execute("SELECT store_json FROM auth_profile_store WHERE store_key = 'primary'").fetchone()[0])
    assert TARGET_PROFILE not in store["profiles"]
    assert "openai:ccnode-codex" in store["profiles"]
    updated = json.loads(config.read_text())
    assert TARGET_PROFILE not in updated["auth"]["profiles"]
    assert "openai" not in updated["auth"]["order"]
    assert not any(migrate(db, (config,), dry_run=False).values())
