from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_runtime_guard_degrades_cleanly_when_upstream_layout_changes() -> None:
    guard = (ROOT / "scripts/openclaw/ensure_agent_society_runtime_guard.sh").read_text(encoding="utf-8")
    assert "runtime patch skipped or incompatible with current OpenClaw layout" in guard
    assert 'runtime_patch_ok=0' in guard
    assert 'AGENT_SOCIETY_RUNTIME_PATCH_OK="$runtime_patch_ok"' in guard
    assert "gateway startup will continue" in guard


def test_installer_makes_startup_guard_non_blocking() -> None:
    installer = (ROOT / "scripts/remote_install_agent_society_startup_guard.py").read_text(encoding="utf-8")
    assert "ExecStartPre=-/usr/local/lib/openclaw/ensure_agent_society_runtime_guard.sh" in installer
    assert "gateway startup will continue" in installer
