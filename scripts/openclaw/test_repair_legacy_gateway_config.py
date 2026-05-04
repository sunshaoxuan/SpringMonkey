from __future__ import annotations

import json
import tempfile
from pathlib import Path

from repair_legacy_gateway_config import load_json, repair_config, repair_config_data


def test_repair_config_data_removes_startup_blockers() -> None:
    data = {
        "agents": {"defaults": {"llm": {"timeout": 120}, "other": True}},
        "tools": {"web": {"search": {"enabled": True, "provider": "brave"}}},
        "plugins": {"slots": {"memory": "memory-lancedb"}},
    }

    actions = repair_config_data(data)

    assert "removed legacy agents.defaults.llm" in actions
    assert "disabled unavailable brave web_search provider" in actions
    assert "cleared unavailable memory-lancedb plugin slot" in actions
    assert "llm" not in data["agents"]["defaults"]
    assert data["tools"]["web"]["search"] == {"enabled": False}
    assert "slots" not in data["plugins"]


def test_repair_config_writes_backup_and_is_idempotent() -> None:
    with tempfile.TemporaryDirectory(prefix="openclaw_config_repair_") as tmp:
        path = Path(tmp) / "openclaw.json"
        path.write_text(
            json.dumps(
                {
                    "agents": {"defaults": {"llm": "legacy"}},
                    "tools": {"web": {"search": {"provider": "brave"}}},
                }
            ),
            encoding="utf-8",
        )

        first = repair_config(path, backup_suffix="test")
        second = repair_config(path, backup_suffix="test2")

        assert first.changed is True
        assert first.backup is not None
        assert first.backup.exists()
        assert second.changed is False
        assert load_json(path)["tools"]["web"]["search"] == {"enabled": False}


if __name__ == "__main__":
    test_repair_config_data_removes_startup_blockers()
    test_repair_config_writes_backup_and_is_idempotent()
    print("test_repair_legacy_gateway_config_ok")
