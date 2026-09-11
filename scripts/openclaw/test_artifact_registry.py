from __future__ import annotations

import json
from pathlib import Path

import pytest

import artifact_registry


def test_record_and_load_latest_artifact(tmp_path: Path) -> None:
    state = tmp_path / "latest.json"

    recorded = artifact_registry.record_artifact(
        "See https://docs.google.com/document/d/current/edit?tab=t.0.",
        "xhs-recommendation-every-3-days",
        path=state,
    )

    assert recorded["url"] == "https://docs.google.com/document/d/current/edit?tab=t.0"
    assert artifact_registry.load_latest_artifact(state) == recorded
    assert json.loads(state.read_text(encoding="utf-8"))["source"] == "xhs-recommendation-every-3-days"


def test_record_rejects_non_google_document_url(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="valid Google Docs"):
        artifact_registry.record_artifact("https://example.com/file", "test", path=tmp_path / "latest.json")
