#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    path = Path(__file__).with_name("local_sync_openclaw_recovery_bundle.py")
    spec = importlib.util.spec_from_file_location("local_sync_openclaw_recovery_bundle", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prune_local_bundles_keeps_only_latest(tmp_path: Path) -> None:
    module = load_module()
    for name in [
        "openclaw-recovery-20260610-042009.tar.gz",
        "openclaw-recovery-20260611-042011.tar.gz",
        "openclaw-recovery-20260612-042008.tar.gz",
    ]:
        (tmp_path / name).write_text("bundle", encoding="utf-8")

    module.prune_local_bundles(tmp_path)

    assert [path.name for path in tmp_path.glob("openclaw-recovery-*.tar.gz")] == [
        "openclaw-recovery-20260612-042008.tar.gz"
    ]
