#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_KERNEL_ROOT = Path("/var/lib/openclaw/.openclaw/workspace/agent_society_kernel")


@dataclass
class ToolsmithPackage:
    package_id: str
    status: str
    gap_type: str
    safety_class: str
    tool_id: str
    entrypoint: str
    permission_scope: str
    write_operation: bool
    verify_command: str
    replay_policy: str
    package_dir: str
    registry_patch: dict[str, Any]
    files: list[str]
    reason: str
    created_at: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug[:80] or "capability_repair"


def classify_gap(reason: str, registry_tool: dict[str, Any] | None = None) -> str:
    lowered = reason.lower()
    if "permission" in lowered or "governance" in lowered or "denied" in lowered:
        return "permission_missing"
    if "entrypoint" in lowered or "no such file" in lowered or "not found" in lowered:
        return "entrypoint_missing"
    if "test" in lowered or "verify" in lowered:
        return "test_missing"
    if registry_tool:
        return "runtime_missing"
    return "registry_missing"


def infer_tool_id(text: str, gap_type: str) -> str:
    if re.search(r"(天气|weather|風|风|能见度)", text, re.IGNORECASE):
        return "weather.dm.generated_readonly"
    if re.search(r"(小红书|小紅書|xhs|长记忆|memory)", text, re.IGNORECASE):
        return "memory.generated_readonly"
    return f"openclaw.generated.{safe_slug(gap_type)}"


def render_helper(tool_id: str) -> str:
    return f'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser(description="Generated read-only helper draft for {tool_id}.")
    parser.add_argument("--text", default="")
    parser.add_argument("--message-timestamp", default="")
    args = parser.parse_args()
    print(json.dumps({{"status": "draft", "tool_id": "{tool_id}", "text": args.text}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def render_test(entrypoint: str) -> str:
    return f'''from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_generated_helper_draft_runs() -> None:
    repo = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, str(repo / "{entrypoint}"), "--text", "smoke"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert "draft" in proc.stdout
'''


def build_registry_patch(tool_id: str, entrypoint: str, text: str) -> dict[str, Any]:
    return {
        "intent_id": tool_id,
        "tool_id": tool_id,
        "description": f"Generated read-only repair helper for: {text[:120]}",
        "patterns": [text[:20] or "generated"],
        "required_any": [],
        "entrypoint": entrypoint,
        "args_schema": {"mode": "dm_text_timestamp", "force": False},
        "permission": "owner_dm",
        "permission_scope": "owner_dm_readonly",
        "write_operation": False,
        "verify_command": f"python -m compileall -q {entrypoint}",
        "failure_policy": "reply_failure_and_record_gap",
        "reply_policy": "tool_stdout",
        "capability_id": tool_id,
        "domain": "general",
        "actions": ["query"],
        "safety": "readonly",
    }


def generate_repair_package(
    *,
    text: str,
    reason: str,
    safety_class: str,
    kernel_root: Path,
    repo_root: Path,
    registry_tool: dict[str, Any] | None = None,
    apply_readonly: bool = False,
) -> ToolsmithPackage:
    gap_type = classify_gap(reason, registry_tool)
    write_like = safety_class in {"requires_confirmation_or_credentials"} or bool((registry_tool or {}).get("write_operation"))
    tool_id = str((registry_tool or {}).get("tool_id") or infer_tool_id(text, gap_type))
    entrypoint = str((registry_tool or {}).get("entrypoint") or f"scripts/openclaw/helpers/generated_{safe_slug(tool_id)}.py")
    package_id = f"repair_{safe_slug(tool_id)}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    package_dir = kernel_root / "toolsmith_packages" / package_id
    package_dir.mkdir(parents=True, exist_ok=True)
    registry_patch = build_registry_patch(tool_id, entrypoint, text)
    files: list[str] = []
    status = "blocked_requires_authorization" if write_like else "generated"
    replay_policy = "blocked_until_human_authorization" if write_like else "verify_before_replay"
    if not write_like:
        helper_rel = Path(entrypoint)
        test_rel = Path("scripts/openclaw") / f"test_generated_{safe_slug(tool_id)}.py"
        (package_dir / helper_rel.name).write_text(render_helper(tool_id), encoding="utf-8")
        (package_dir / test_rel.name).write_text(render_test(entrypoint), encoding="utf-8")
        (package_dir / "registry_patch.json").write_text(json.dumps(registry_patch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files = [str(package_dir / helper_rel.name), str(package_dir / test_rel.name), str(package_dir / "registry_patch.json")]
        if apply_readonly:
            target_helper = repo_root / helper_rel
            target_helper.parent.mkdir(parents=True, exist_ok=True)
            target_helper.write_text(render_helper(tool_id), encoding="utf-8")
            target_test = repo_root / test_rel
            target_test.write_text(render_test(entrypoint), encoding="utf-8")
            files.extend([str(target_helper), str(target_test)])
            status = "generated_applied"
    else:
        (package_dir / "authorization_required.json").write_text(json.dumps({
            "tool_id": tool_id,
            "reason": reason,
            "safety_class": safety_class,
            "registry_tool": registry_tool,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files = [str(package_dir / "authorization_required.json")]
    return ToolsmithPackage(
        package_id=package_id,
        status=status,
        gap_type=gap_type,
        safety_class=safety_class,
        tool_id=tool_id,
        entrypoint=entrypoint,
        permission_scope="owner_dm_readonly" if not write_like else str((registry_tool or {}).get("permission_scope") or "requires_authorization"),
        write_operation=write_like,
        verify_command=str(registry_patch.get("verify_command") or ""),
        replay_policy=replay_policy,
        package_dir=str(package_dir),
        registry_patch=registry_patch,
        files=files,
        reason=reason,
        created_at=utc_now(),
    )


def append_package_log(kernel_root: Path, package: ToolsmithPackage) -> Path:
    path = kernel_root / "toolsmith_repair_packages.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(package), ensure_ascii=False, sort_keys=True) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate bounded toolsmith repair packages for capability gaps.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--safety-class", default="unsupported_or_ambiguous")
    parser.add_argument("--kernel-root", type=Path, default=DEFAULT_KERNEL_ROOT)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--registry-tool-json", default="")
    parser.add_argument("--apply-readonly", action="store_true")
    args = parser.parse_args()
    registry_tool = json.loads(args.registry_tool_json) if args.registry_tool_json else None
    package = generate_repair_package(
        text=args.text,
        reason=args.reason,
        safety_class=args.safety_class,
        kernel_root=args.kernel_root,
        repo_root=args.repo_root,
        registry_tool=registry_tool,
        apply_readonly=args.apply_readonly,
    )
    append_package_log(args.kernel_root, package)
    print(json.dumps(asdict(package), ensure_ascii=False, indent=2))
    return 0 if package.status in {"generated", "generated_applied", "blocked_requires_authorization"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
