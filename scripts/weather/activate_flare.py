"""Switch only the existing daily weather cron entry to Flare."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import shutil
import stat
import tempfile


MODEL_SETTING = "OPENCLAW_WEATHER_IMAGE_MODEL_CANDIDATES=openai/gpt-image-2.5-flare"


def configured_cron(source: str) -> str:
    lines = source.splitlines(keepends=True)
    matches = []
    for index, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        tokens = shlex.split(line)
        if "--name" in tokens and tokens[tokens.index("--name") + 1] == "weather-report-jst-0700":
            matches.append((index, tokens))
    if len(matches) != 1:
        raise ValueError("Expected exactly one existing daily weather entry")
    index, tokens = matches[0]
    settings = [token for token in tokens if token.startswith("OPENCLAW_WEATHER_IMAGE_MODEL_CANDIDATES=")]
    if len(settings) != 1:
        raise ValueError("Expected one explicit weather model setting")
    lines[index] = lines[index].replace(settings[0], MODEL_SETTING, 1)
    return "".join(lines)


def main() -> int:
    from PIL import Image

    # Verify the image-processing dependency before changing the scheduled job.
    Image.Resampling.LANCZOS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=Path("/etc/cron.d/openclaw-direct-discord"))
    args = parser.parse_args()
    source = args.path.read_text(encoding="utf-8")
    updated = configured_cron(source)
    if source == updated:
        print("WEATHER_MODEL=already-flare")
        return 0
    backup = args.path.with_name(args.path.name + ".pre-flare-20260915.bak")
    if not backup.exists():
        shutil.copy2(args.path, backup)
    original = args.path.stat()
    fd, temporary = tempfile.mkstemp(prefix=".weather-flare-", dir=args.path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(original.st_mode))
        if hasattr(os, "chown"):
            os.chown(temporary, original.st_uid, original.st_gid)
        os.replace(temporary, args.path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    assert args.path.read_text(encoding="utf-8") == updated
    print("WEATHER_MODEL=flare")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
