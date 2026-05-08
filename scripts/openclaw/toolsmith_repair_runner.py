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

try:
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


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
    semantic_source: str = ""
    deployment_status: str = "not_requested"


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


def registry_tools(repo_root: Path) -> list[dict[str, Any]]:
    registry_path = repo_root / "config" / "openclaw" / "intent_tools.json"
    if not registry_path.is_file():
        return []
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    tools = data.get("tools", [])
    return tools if isinstance(tools, list) else []


def infer_domain_actions(text: str, gap_type: str) -> tuple[str, list[str]]:
    if re.search(r"(小红书|小紅書|xhs|长记忆|memory|记忆|記憶)", text, re.IGNORECASE):
        return "memory", ["query"]
    if re.search(r"(天气|weather|風|风|能见度|視程|可視性)", text, re.IGNORECASE):
        return "weather", ["query"]
    if re.search(r"(状态|狀態|自演进|自進化|能力缺口|修复包|修復包)", text, re.IGNORECASE):
        return "self", ["status"]
    if gap_type == "entrypoint_missing":
        return "general", ["query"]
    return "general", ["query"]


def score_reference_tool(tool: dict[str, Any], *, domain: str, actions: list[str], readonly: bool, input_type: str) -> int:
    score = 0
    if str(tool.get("domain") or "") == domain:
        score += 8
    tool_actions = tool.get("actions") if isinstance(tool.get("actions"), list) else []
    if any(action in tool_actions for action in actions):
        score += 4
    if bool(tool.get("write_operation")) is not readonly:
        score += 4
    schema = tool.get("input_schema") if isinstance(tool.get("input_schema"), dict) else {}
    contract = tool.get("input_contract") if isinstance(tool.get("input_contract"), dict) else {}
    if input_type in {str(schema.get("type") or ""), str(contract.get("type") or "")}:
        score += 2
    if str(tool.get("safety") or "") == "readonly" and readonly:
        score += 1
    args_schema = tool.get("args_schema") if isinstance(tool.get("args_schema"), dict) else {}
    if readonly and bool(args_schema.get("write")):
        score -= 4
    if "query" in actions and "backfill" in tool_actions:
        score -= 3
    return score


def find_reference_tool(repo_root: Path, *, text: str, gap_type: str, readonly: bool = True) -> dict[str, Any] | None:
    domain, actions = infer_domain_actions(text, gap_type)
    input_type = "dm_text_timestamp"
    candidates = [
        tool
        for tool in registry_tools(repo_root)
        if bool(tool.get("write_operation")) is not readonly
    ]
    ranked = sorted(
        candidates,
        key=lambda tool: score_reference_tool(tool, domain=domain, actions=actions, readonly=readonly, input_type=input_type),
        reverse=True,
    )
    if ranked and score_reference_tool(ranked[0], domain=domain, actions=actions, readonly=readonly, input_type=input_type) > 0:
        return dict(ranked[0])
    return None


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


def render_semantic_helper(tool_id: str, domain: str, reference_tool_id: str) -> str:
    return f'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


TOOL_ID = "{tool_id}"
DOMAIN = "{domain}"
REFERENCE_TOOL_ID = "{reference_tool_id}"

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def run_command(args: list[str], timeout: int = 20) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=repo_root(),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return proc.returncode == 0, (proc.stdout or "").strip()
    except Exception as exc:
        return False, f"{{type(exc).__name__}}: {{exc}}"


def memory_query(text: str) -> str:
    query = text or "小红书 Costco Frutteto 投稿"
    ok, output = run_command(["openclaw", "ltm", "search", query, "--limit", "5"], timeout=40)
    if ok and output:
        return output
    return "长记忆查询未返回结果；请检查 memory-lancedb 或 embedding/text fallback。"


def self_status() -> str:
    ok, output = run_command([sys.executable, "scripts/openclaw/self_evolution_status.py", "--limit", "5"])
    return output if ok and output else "自演进状态暂不可用。"


def config_check() -> str:
    registry = repo_root() / "config" / "openclaw" / "intent_tools.json"
    if not registry.is_file():
        return "未找到 intent tool registry。"
    data = json.loads(registry.read_text(encoding="utf-8"))
    tools = data.get("tools", [])
    return f"注册工具数量：{{len(tools)}}；参考工具：{{REFERENCE_TOOL_ID}}。"


def answer(text: str) -> str:
    combined = f"{{text}} {{DOMAIN}}"
    if DOMAIN == "memory" or re.search(r"长记忆|記憶|memory|小红书|xhs", combined, re.I):
        return memory_query(text)
    if DOMAIN == "self" or re.search(r"自演进|自進化|能力缺口|修复包|修復包|状态|狀態", combined, re.I):
        return self_status()
    if re.search(r"配置|注册|registry|工具", combined, re.I):
        return config_check()
    return f"只读语义 helper 已处理请求：{{text or '未提供文本'}}"


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Semantic read-only helper generated for {{TOOL_ID}}.")
    parser.add_argument("--text", default="")
    parser.add_argument("--message-timestamp", default="")
    parser.add_argument("--topic", default="")
    parser.add_argument("--since", default="")
    parser.add_argument("--write", default="false")
    parser.add_argument("--forget-marked", default="false")
    parser.add_argument("--limit", default="")
    args, _unknown = parser.parse_known_args()
    result = answer(args.text)
    print(json.dumps({{
        "status": "success",
        "tool_id": TOOL_ID,
        "domain": DOMAIN,
        "reference_tool_id": REFERENCE_TOOL_ID,
        "result": result,
        "trace": {{
            "semantic_helper": True,
            "message_timestamp": args.message_timestamp,
        }},
    }}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def render_test(entrypoint: str, *, semantic: bool = False) -> str:
    if semantic:
        return f'''from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_generated_semantic_helper_runs_with_business_contract() -> None:
    repo = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, str(repo / "{entrypoint}"), "--text", "检查自演进状态"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["status"] == "success"
    assert payload["tool_id"]
    assert payload["result"]
    assert "draft" not in proc.stdout.lower()
    assert payload["trace"]["semantic_helper"] is True
'''
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


def build_registry_patch(
    tool_id: str,
    entrypoint: str,
    text: str,
    *,
    reference_tool: dict[str, Any] | None = None,
    semantic: bool = False,
) -> dict[str, Any]:
    prompt = text[:40] or "generated"
    domain, actions = infer_domain_actions(text, "registry_missing")
    args_schema = dict((reference_tool or {}).get("args_schema") or {"mode": "dm_text_timestamp", "force": False})
    if semantic:
        args_schema["force"] = False
        if "write" in args_schema:
            args_schema["write"] = False
        if "forget_marked" in args_schema:
            args_schema["forget_marked"] = False
    patch = {
        "intent_id": tool_id,
        "tool_id": tool_id,
        "description": f"Generated semantic read-only repair helper for: {text[:120]}" if semantic else f"Generated read-only repair helper for: {text[:120]}",
        "owner_agent": str((reference_tool or {}).get("owner_agent") or "toolWorker"),
        "patterns": [prompt],
        "required_any": [],
        "entrypoint": entrypoint,
        "args_schema": args_schema,
        "permission": str((reference_tool or {}).get("permission") or "owner_dm"),
        "permission_scope": str((reference_tool or {}).get("permission_scope") or "owner_dm_readonly"),
        "write_operation": False,
        "input_schema": dict((reference_tool or {}).get("input_schema") or {"type": "dm_text_timestamp"}),
        "output_schema": dict((reference_tool or {}).get("output_schema") or {"type": "plain_text_business_result", "requires_trace": True}),
        "invocation_log_policy": str((reference_tool or {}).get("invocation_log_policy") or "harness_tool_invocation_jsonl"),
        "verify_command": f"python -m compileall -q {entrypoint}",
        "failure_policy": str((reference_tool or {}).get("failure_policy") or "reply_failure_and_record_gap"),
        "reply_policy": str((reference_tool or {}).get("reply_policy") or "tool_stdout"),
        "capability_id": tool_id,
        "domain": str((reference_tool or {}).get("domain") or domain),
        "actions": list((reference_tool or {}).get("actions") or actions),
        "worker_agent": str((reference_tool or {}).get("worker_agent") or "toolWorker"),
        "prompt_hints": [prompt],
        "input_contract": dict((reference_tool or {}).get("input_contract") or {"type": "dm_text_timestamp"}),
        "output_contract": dict((reference_tool or {}).get("output_contract") or {"type": "plain_text_business_result"}),
        "safety": "readonly",
        "implementation_status": "ready" if semantic else "candidate_draft",
    }
    if reference_tool:
        patch["semantic_reference_tool_id"] = reference_tool.get("tool_id")
    return patch


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
    semantic: bool = False,
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
    reference_tool = find_reference_tool(repo_root, text=text, gap_type=gap_type, readonly=True) if semantic and not write_like else None
    registry_patch = build_registry_patch(tool_id, entrypoint, text, reference_tool=reference_tool, semantic=semantic and not write_like)
    files: list[str] = []
    status = "blocked_requires_authorization" if write_like else "generated"
    replay_policy = "blocked_until_human_authorization" if write_like else "verify_before_replay"
    if not write_like:
        helper_rel = Path(entrypoint)
        test_rel = Path("scripts/openclaw") / f"test_generated_{safe_slug(tool_id)}.py"
        domain = str(registry_patch.get("domain") or infer_domain_actions(text, gap_type)[0])
        helper_text = (
            render_semantic_helper(tool_id, domain, str((reference_tool or {}).get("tool_id") or "none"))
            if semantic
            else render_helper(tool_id)
        )
        test_text = render_test(entrypoint, semantic=semantic)
        (package_dir / helper_rel.name).write_text(helper_text, encoding="utf-8")
        (package_dir / test_rel.name).write_text(test_text, encoding="utf-8")
        (package_dir / "registry_patch.json").write_text(json.dumps(registry_patch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files = [str(package_dir / helper_rel.name), str(package_dir / test_rel.name), str(package_dir / "registry_patch.json")]
        if apply_readonly:
            target_helper = repo_root / helper_rel
            target_helper.parent.mkdir(parents=True, exist_ok=True)
            target_helper.write_text(helper_text, encoding="utf-8")
            target_test = repo_root / test_rel
            target_test.write_text(test_text, encoding="utf-8")
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
        semantic_source=str((reference_tool or {}).get("tool_id") or ("registry_tool_contract" if semantic and not write_like else "")),
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


def mark_deployed(package: ToolsmithPackage) -> ToolsmithPackage:
    if package.status == "promoted" and not package.write_operation:
        package.status = "deployed"
        package.deployment_status = "git_deploy_requested"
        package.verify_output = "\n".join([package.verify_output, "deployment_status=git_deploy_requested"]).strip()
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
    parser.add_argument("--semantic", action="store_true")
    parser.add_argument("--mark-deployed", action="store_true")
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
        semantic=args.semantic,
    )
    if args.verify_promote:
        package = verify_and_promote_package(package, kernel_root=args.kernel_root, repo_root=args.repo_root)
    if args.mark_deployed:
        package = mark_deployed(package)
    append_package_log(args.kernel_root, package)
    print(json.dumps(asdict(package), ensure_ascii=False, indent=2))
    return 0 if package.status in {"generated", "generated_applied", "verified", "promoted", "deployed", "blocked_requires_authorization"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
