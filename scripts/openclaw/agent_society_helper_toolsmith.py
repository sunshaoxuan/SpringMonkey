#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


TEMPLATE = """#!/usr/bin/env python3
from __future__ import annotations

import json


def main() -> int:
    payload = {{
        "helper_name": "{helper_name}",
        "purpose": "{purpose}",
        "status": "scaffold",
        "notes": "replace this scaffold with a validated bounded helper implementation",
    }}
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def normalize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "helper_tool"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a bounded helper-tool scaffold in the repo.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--helper-name", required=True)
    parser.add_argument("--purpose", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root)
    target_dir = repo_root / "scripts" / "openclaw" / "helpers"
    target_dir.mkdir(parents=True, exist_ok=True)

    slug = normalize_slug(args.helper_name)
    target = target_dir / f"{slug}.py"
    if not target.exists():
        target.write_text(TEMPLATE.format(helper_name=args.helper_name, purpose=args.purpose), encoding="utf-8")
    target.chmod(0o755)

    print(json.dumps({
        "helper_name": args.helper_name,
        "entrypoint": str(target.relative_to(repo_root)).replace("\\", "/"),
        "created": True,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
