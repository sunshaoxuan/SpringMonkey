from __future__ import annotations

from pathlib import Path

import verify_harness_flow_exits as verifier


def test_flow_exit_guard_passes_current_semantic_layers() -> None:
    findings = []
    for path in verifier.SEMANTIC_FILES:
        if path.is_file():
            findings.extend(verifier.scan_semantic_file(path))
    for path in verifier.MID_EXIT_FILES:
        if path.is_file():
            findings.extend(verifier.scan_mid_exits(path))

    assert findings == []


def test_flow_exit_guard_rejects_semantic_regex(tmp_path: Path) -> None:
    source = tmp_path / "router.py"
    source.write_text(
        "import re\n"
        "def decide(text):\n"
        "    return re.search('订车', text)\n",
        encoding="utf-8",
    )

    findings = verifier.scan_semantic_file(source)

    assert findings
    assert "regex" in findings[0].message


def test_flow_exit_guard_allows_low_level_parser_regex(tmp_path: Path) -> None:
    source = tmp_path / "router.py"
    source.write_text(
        "import re\n"
        "def extract_args(tool, text, timestamp):\n"
        "    return re.search('rid=(\\\\d+)', text)\n",
        encoding="utf-8",
    )

    assert verifier.scan_semantic_file(source) == []
