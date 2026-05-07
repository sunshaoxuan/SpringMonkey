#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
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
    fingerprint: str = ""
    verify_output: str = ""
    promoted_at: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug[:80] or "capability_repair"


def repair_fingerprint(*, text: str, reason: str, tool_id: str, entrypoint: str) -> str:
    normalized = json.dumps(
        {
            "text": re.sub(r"\s+", " ", text).strip()[:500],
            "reason": re.sub(r"\s+", " ", reason).strip()[:500],
            "tool_id": tool_id,
            "entrypoint": entrypoint,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


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
    prompt = text[:40] or "generated"
    return {
        "intent_id": tool_id,
        "tool_id": tool_id,
        "description": f"Generated read-only repair helper for: {text[:120]}",
        "owner_agent": "toolWorker",
        "patterns": [prompt],
        "required_any": [],
        "entrypoint": entrypoint,
        "args_schema": {"mode": "dm_text_timestamp", "force": False},
        "permission": "owner_dm",
        "permission_scope": "owner_dm_readonly",
        "write_operation": False,
        "input_schema": {"type": "dm_text_timestamp"},
        "output_schema": {"type": "plain_text_business_result", "requires_trace": True},
        "invocation_log_policy": "harness_tool_invocation_jsonl",
        "verify_command": f"python -m compileall -q {entrypoint}",
        "failure_policy": "reply_failure_and_record_gap",
        "reply_policy": "tool_stdout",
        "capability_id": tool_id,
        "domain": "general",
        "actions": ["query"],
        "worker_agent": "toolWorker",
        "prompt_hints": [prompt],
        "input_contract": {"type": "dm_text_timestamp"},
        "output_contract": {"type": "plain_text_business_result"},
        "safety": "readonly",
        "implementation_status": "candidate_draft",
    }


def package_state_path(package_dir: Path) -> Path:
    return package_dir / "package_state.json"


def save_package_state(package: ToolsmithPackage) -> None:
    package_state_path(Path(package.package_dir)).write_text(
        json.dumps(asdict(package), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_package_state(package_dir: Path) -> ToolsmithPackage | None:
    state_path = package_state_path(package_dir)
    if not state_path.is_file():
        return None
    return ToolsmithPackage(**json.loads(state_path.read_text(encoding="utf-8")))


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
    fingerprint = repair_fingerprint(text=text, reason=reason, tool_id=tool_id, entrypoint=entrypoint)
    package_id = f"repair_{safe_slug(tool_id)}_{fingerprint}"
    package_dir = kernel_root / "toolsmith_packages" / package_id
    package_dir.mkdir(parents=True, exist_ok=True)
    existing = load_package_state(package_dir)
    if existing is not None:
        return existing
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
    package = ToolsmithPackage(
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
        fingerprint=fingerprint,
    )
    save_package_state(package)
    return package


def append_package_log(kernel_root: Path, package: ToolsmithPackage) -> Path:
    path = kernel_root / "toolsmith_repair_packages.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(package), ensure_ascii=False, sort_keys=True) + "\n")
    return path


def run_command(command: str, repo_root: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        command,
        cwd=repo_root,
        shell=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc.returncode == 0, (proc.stdout or "").strip()


def apply_registry_patch(repo_root: Path, registry_patch: dict[str, Any]) -> tuple[bool, str]:
    registry_path = repo_root / "config" / "openclaw" / "intent_tools.json"
    if not registry_path.is_file():
        return False, f"registry not found: {registry_path}"
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    tools = data.setdefault("tools", [])
    tool_id = str(registry_patch.get("tool_id") or "")
    existing = next((item for item in tools if str(item.get("tool_id")) == tool_id), None)
    if existing:
        existing.update(registry_patch)
    else:
        tools.append(registry_patch)
    registry_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True, f"registry patched: {tool_id}"


def register_promoted_helper(kernel_root: Path, package: ToolsmithPackage) -> str:
    from agent_society_kernel import AgentSocietyKernel

    kernel = AgentSocietyKernel(kernel_root)
    record = kernel.register_promoted_helper(
        name=package.tool_id,
        scope=package.permission_scope,
        kind="deterministic_readonly_helper",
        entrypoint=package.entrypoint,
        source_tool_id=package.tool_id,
        source_gap_category=package.gap_type,
        validation_observation=json.dumps(
            {
                "package_id": package.package_id,
                "status": package.status,
                "verify_output": package.verify_output[-2000:],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        helper_contract={
            "tool_id": package.tool_id,
            "entrypoint": package.entrypoint,
            "permission_scope": package.permission_scope,
            "write_operation": package.write_operation,
        },
        repair_workflow=[
            {"status": "generated", "evidence": "toolsmith package created"},
            {"status": "verified", "evidence": "helper test and registry checks passed"},
            {"status": "promoted", "evidence": "durable helper registry updated"},
        ],
        drift={"ok": True, "reasons": []},
    )
    return record.record_id


def verify_and_promote_package(package: ToolsmithPackage, *, kernel_root: Path, repo_root: Path) -> ToolsmithPackage:
    output: list[str] = []
    if package.write_operation:
        package.status = "blocked_requires_authorization"
        package.verify_output = "write-operation repair packages require explicit authorization"
        save_package_state(package)
        return package
    if package.status == "promoted":
        return package
    if str(package.registry_patch.get("implementation_status") or "") != "ready":
        package.status = "generated"
        package.verify_output = "promotion deferred: generated helper is a candidate draft and is not semantically ready"
        save_package_state(package)
        return package
    registry_path = repo_root / "config" / "openclaw" / "intent_tools.json"
    if not registry_path.is_file():
        package.status = "generated"
        package.verify_output = f"formal registry unavailable, promotion deferred: {registry_path}"
        save_package_state(package)
        return package
    helper_rel = Path(package.entrypoint)
    source_helper = Path(package.package_dir) / helper_rel.name
    if not source_helper.is_file():
        package.status = "failed"
        package.verify_output = f"generated helper missing from package: {source_helper}"
        save_package_state(package)
        return package
    target_helper = repo_root / helper_rel
    target_helper.parent.mkdir(parents=True, exist_ok=True)
    target_helper.write_text(source_helper.read_text(encoding="utf-8"), encoding="utf-8")
    test_source = next(Path(package.package_dir).glob("test_generated_*.py"), None)
    if test_source is not None:
        target_test = repo_root / "scripts" / "openclaw" / test_source.name
        target_test.write_text(test_source.read_text(encoding="utf-8"), encoding="utf-8")
        command = f"python -m pytest -q scripts/openclaw/{test_source.name}"
        ok, cmd_output = run_command(command, repo_root)
        output.append(f"$ {command}\n{cmd_output or 'ok'}")
        if not ok:
            package.status = "failed"
            package.verify_output = "\n".join(output)
            save_package_state(package)
            return package
    command = package.verify_command or f"python -m compileall -q {package.entrypoint}"
    ok, cmd_output = run_command(command, repo_root)
    output.append(f"$ {command}\n{cmd_output or 'ok'}")
    if not ok:
        package.status = "failed"
        package.verify_output = "\n".join(output)
        save_package_state(package)
        return package
    ok, patch_output = apply_registry_patch(repo_root, package.registry_patch)
    output.append(patch_output)
    if not ok:
        package.status = "failed"
        package.verify_output = "\n".join(output)
        save_package_state(package)
        return package
    for command in (
        "python scripts/openclaw/verify_intent_tool_registry.py",
        "python scripts/openclaw/verify_harness_registry.py",
    ):
        ok, cmd_output = run_command(command, repo_root)
        output.append(f"$ {command}\n{cmd_output or 'ok'}")
        if not ok:
            package.status = "failed"
            package.verify_output = "\n".join(output)
            save_package_state(package)
            return package
    package.status = "verified"
    package.verify_output = "\n".join(output)
    record_id = register_promoted_helper(kernel_root, package)
    package.status = "promoted"
    package.promoted_at = utc_now()
    package.verify_output = "\n".join([package.verify_output, f"promoted_helper_record={record_id}"])
    save_package_state(package)
    return package


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate bounded toolsmith repair packages for capability gaps.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--safety-class", default="unsupported_or_ambiguous")
    parser.add_argument("--kernel-root", type=Path, default=DEFAULT_KERNEL_ROOT)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--registry-tool-json", default="")
    parser.add_argument("--apply-readonly", action="store_true")
    parser.add_argument("--verify-promote", action="store_true")
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
    if args.verify_promote:
        package = verify_and_promote_package(package, kernel_root=args.kernel_root, repo_root=args.repo_root)
    append_package_log(args.kernel_root, package)
    print(json.dumps(asdict(package), ensure_ascii=False, indent=2))
    return 0 if package.status in {"generated", "generated_applied", "verified", "promoted", "blocked_requires_authorization"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
