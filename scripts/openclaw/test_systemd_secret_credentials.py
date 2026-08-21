from __future__ import annotations

from unittest.mock import patch

import systemd_secret_credentials as credentials


def test_reads_string_secret_from_credential_payload(tmp_path) -> None:
    (tmp_path / credentials.CREDENTIAL_FILENAME).write_text('{"channels":{"discord":{"token":"test-token"}}}', encoding="utf-8")
    with patch.dict(credentials.os.environ, {"CREDENTIALS_DIRECTORY": str(tmp_path)}, clear=False):
        assert credentials.read_systemd_secret("channels", "discord", "token") == "test-token"


def test_returns_empty_for_missing_payload(tmp_path) -> None:
    with patch.dict(credentials.os.environ, {"CREDENTIALS_DIRECTORY": str(tmp_path)}, clear=False):
        assert credentials.read_systemd_secret("channels", "discord", "token") == ""
