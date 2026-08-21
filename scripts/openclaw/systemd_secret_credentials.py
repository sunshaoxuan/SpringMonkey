from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CREDENTIALS_DIRECTORY = Path("/run/credentials/openclaw.service")
CREDENTIAL_FILENAME = "openclaw-secrets.json"


def read_systemd_secret(*segments: str) -> str:
    """Return one string secret from the active systemd credential payload."""
    if not segments:
        return ""
    credential_dir = Path(os.environ.get("CREDENTIALS_DIRECTORY", str(DEFAULT_CREDENTIALS_DIRECTORY)))
    try:
        value: Any = json.loads((credential_dir / CREDENTIAL_FILENAME).read_text(encoding="utf-8"))
        for segment in segments:
            value = value[segment]
        return value.strip() if isinstance(value, str) else ""
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return ""
