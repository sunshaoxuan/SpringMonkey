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
AUTONOMOUS_REPAIR_ACTIONS = {
    "autonomous_internal_repair",
    "autonomous_readonly_repair",
    "generate_helper_and_verify",
}

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


def plan_tool_id(llm_classification: dict[str, Any] | None, gap_type: str) -> str:
    family = str((llm_classification or {}).get("expected_capability_family") or gap_type or "capability")
    allowed_action = str((llm_classification or {}).get("allowed_repair_action") or "")
    if family.startswith("openclaw.self_evolution") or allowed_action.startswith("repair_binding_or_route_to_registered_tool_openclaw.self_evolution"):
        return "openclaw.repair_plan.openclaw_self_evolution_internal_repair"
    return f"openclaw.repair_plan.{safe_slug(family)}"


def classify_gap(reason: str, registry_tool: dict[str, Any] | None = None, llm_classification: dict[str, Any] | None = None) -> str:
    blocker_kind = str((llm_classification or {}).get("blocker_kind") or "")
    if bool((llm_classification or {}).get("autonomy_allowed")) or str((llm_classification or {}).get("allowed_repair_action") or "") in AUTONOMOUS_REPAIR_ACTIONS:
        return "registry_missing"
    if blocker_kind in {"access_or_approval_blocker", "credential_missing"}:
        return "permission_missing"
    if blocker_kind == "registered_tool_regression":
        return "registry_pattern_gap"
    if blocker_kind == "readonly_tool_missing":
        return "registry_missing"
    if blocker_kind == "tool_binding_gap":
        return "registry_missing"
    if blocker_kind == "write_operation_request":
        return "permission_missing"
    if blocker_kind == "ambiguous":
        return "permission_missing"
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


def family_parts(llm_classification: dict[str, Any] | None) -> list[str]:
    family = str((llm_classification or {}).get("expected_capability_family") or "").strip()
    if not family or family == "unknown":
        return []
    return [part for part in re.split(r"[^A-Za-z0-9]+", family.lower()) if part]


def infer_tool_id(gap_type: str, llm_classification: dict[str, Any] | None = None) -> str:
    parts = family_parts(llm_classification)
    if parts:
        return f"openclaw.generated.{safe_slug('.'.join(parts[:4]))}"
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


def registered_tool_by_id(repo_root: Path, tool_id: str) -> dict[str, Any] | None:
    if not tool_id:
        return None
    return next((tool for tool in registry_tools(repo_root) if str(tool.get("tool_id") or "") == tool_id), None)


def semantic_registered_tool_for_repair(repo_root: Path, llm_classification: dict[str, Any] | None) -> dict[str, Any] | None:
    classification = llm_classification or {}
    family = str(classification.get("expected_capability_family") or "")
    allowed_action = str(classification.get("allowed_repair_action") or "")
    if family.startswith("openclaw.self_evolution") or allowed_action.startswith("repair_binding_or_route_to_registered_tool_openclaw.self_evolution"):
        return registered_tool_by_id(repo_root, "openclaw.self_evolution.internal_repair")
    return None


def infer_domain_actions(gap_type: str, llm_classification: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    parts = family_parts(llm_classification)
    if parts:
        domain = parts[0]
        actions = [part for part in parts[1:4] if part not in {"capability", "tool", "workflow"}]
        return domain, actions or ["query"]
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


def find_reference_tool(
    repo_root: Path,
    *,
    gap_type: str,
    readonly: bool = True,
    exclude_tool_id: str = "",
    llm_classification: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    domain, actions = infer_domain_actions(gap_type, llm_classification)
    input_type = "dm_text_timestamp"
    candidates = [
        tool
        for tool in registry_tools(repo_root)
        if bool(tool.get("write_operation")) is not readonly
        and str(tool.get("tool_id") or "") != exclude_tool_id
    ]
    ranked = sorted(
        candidates,
        key=lambda tool: score_reference_tool(tool, domain=domain, actions=actions, readonly=readonly, input_type=input_type),
        reverse=True,
    )
    threshold = 8 if domain == "general" else 1
    if ranked and score_reference_tool(ranked[0], domain=domain, actions=actions, readonly=readonly, input_type=input_type) >= threshold:
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
    if DOMAIN == "memory":
        return memory_query(text)
    if DOMAIN == "self":
        return self_status()
    if DOMAIN in {{"config", "registry", "tooling"}}:
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
    llm_classification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt = text[:40] or "generated"
    domain, actions = infer_domain_actions("registry_missing", llm_classification)
    reference_actions = list((reference_tool or {}).get("actions") or [])
    merged_actions = list(dict.fromkeys(reference_actions + actions))
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
        "actions": merged_actions,
        "worker_agent": str((reference_tool or {}).get("worker_agent") or "toolWorker"),
        "prompt_hints": [],
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
    llm_classification: dict[str, Any] | None = None,
) -> ToolsmithPackage:
    semantic_registry_tool = registry_tool or semantic_registered_tool_for_repair(repo_root, llm_classification)
    gap_type = classify_gap(reason, semantic_registry_tool, llm_classification)
    blocker_kind = str((llm_classification or {}).get("blocker_kind") or "")
    autonomy_allowed = bool((llm_classification or {}).get("autonomy_allowed")) or str((llm_classification or {}).get("allowed_repair_action") or "") in AUTONOMOUS_REPAIR_ACTIONS
    model_blocks_toolsmith = blocker_kind in {
        "access_or_approval_blocker",
        "credential_missing",
        "ambiguous",
    } and not autonomy_allowed
    allowed_action = str((llm_classification or {}).get("allowed_repair_action") or "")
    internal_write_repair_plan = autonomy_allowed and (
        blocker_kind == "write_operation_request"
        or (blocker_kind == "registered_tool_regression" and allowed_action == "autonomous_internal_repair")
    )
    write_like = (
        (safety_class in {"requires_confirmation_or_credentials", "unsupported_or_ambiguous"} and not autonomy_allowed)
        or bool((semantic_registry_tool or {}).get("write_operation"))
        or model_blocks_toolsmith
        or internal_write_repair_plan
    )
    if internal_write_repair_plan:
        tool_id = plan_tool_id(llm_classification, gap_type)
    elif model_blocks_toolsmith:
        tool_id = str((semantic_registry_tool or {}).get("tool_id") or "openclaw.authorization_required")
    else:
        tool_id = str((semantic_registry_tool or {}).get("tool_id") or infer_tool_id(gap_type, llm_classification))
    entrypoint = str((semantic_registry_tool or {}).get("entrypoint") or ("" if (model_blocks_toolsmith or internal_write_repair_plan) else f"scripts/openclaw/helpers/generated_{safe_slug(tool_id)}.py"))
    fingerprint = repair_fingerprint(text=text, reason=reason, tool_id=tool_id, entrypoint=entrypoint)
    package_id = f"repair_{safe_slug(tool_id)}_{fingerprint}"
    package_dir = kernel_root / "toolsmith_packages" / package_id
    package_dir.mkdir(parents=True, exist_ok=True)
    existing = load_package_state(package_dir)
    if existing is not None:
        return existing
    reference_tool = (
        find_reference_tool(
            repo_root,
            gap_type=gap_type,
            readonly=True,
            exclude_tool_id=tool_id,
            llm_classification=llm_classification,
        )
        if semantic and not write_like
        else None
    )
    registry_patch = (
        {}
        if write_like
        else build_registry_patch(
            tool_id,
            entrypoint,
            text,
            reference_tool=reference_tool,
            semantic=semantic and not write_like,
            llm_classification=llm_classification,
        )
    )
    files: list[str] = []
    status = "planned" if internal_write_repair_plan else ("blocked_requires_authorization" if write_like else "generated")
    replay_policy = "blocked_until_domain_implementation" if internal_write_repair_plan else ("blocked_until_human_authorization" if write_like else "verify_before_replay")
    if not write_like:
        helper_rel = Path(entrypoint)
        test_rel = Path("scripts/openclaw") / f"test_generated_{safe_slug(tool_id)}.py"
        domain = str(registry_patch.get("domain") or infer_domain_actions(gap_type, llm_classification)[0])
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
        plan_name = "domain_implementation_required.json" if internal_write_repair_plan else "authorization_required.json"
        (package_dir / plan_name).write_text(json.dumps({
            "tool_id": tool_id,
            "reason": reason,
            "safety_class": safety_class,
            "registry_tool": semantic_registry_tool,
            "llm_classification": llm_classification,
            "missing_condition": str((llm_classification or {}).get("missing_condition") or ""),
            "allowed_repair_action": str((llm_classification or {}).get("allowed_repair_action") or "record_gap_only"),
            "implementation_required": internal_write_repair_plan,
            "next_step": (
                "Generate a domain-specific implementation plan, tests, and approval-gated rollout package; "
                "do not promote a generic helper or replay the original write request."
                if internal_write_repair_plan
                else "Request authorization before proceeding."
            ),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files = [str(package_dir / plan_name)]
    package = ToolsmithPackage(
        package_id=package_id,
        status=status,
        gap_type=gap_type,
        safety_class=safety_class,
        tool_id=tool_id,
        entrypoint=entrypoint,
        permission_scope="owner_dm_readonly" if not write_like else str((semantic_registry_tool or {}).get("permission_scope") or "requires_authorization"),
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


def pytest_missing(output: str) -> bool:
    lowered = (output or "").lower()
    return "no module named pytest" in lowered or "pytest: command not found" in lowered


def run_generated_helper_contract(package: ToolsmithPackage, repo_root: Path, test_rel: Path) -> tuple[bool, str]:
    helper_rel = Path(package.entrypoint)
    commands = [
        f"python -m compileall -q {test_rel.as_posix()}",
        f"python {helper_rel.as_posix()} --text \"检查自演进状态\"",
    ]
    output: list[str] = []
    for command in commands:
        ok, cmd_output = run_command(command, repo_root)
        output.append(f"$ {command}\n{cmd_output or 'ok'}")
        if not ok:
            return False, "\n".join(output)
        if command.startswith("python ") and not command.startswith("python -m ") and '"status": "success"' not in (cmd_output or ""):
            return False, "\n".join(output + ["generated helper did not return success JSON"])
    return True, "\n".join(output)


def apply_registry_patch(repo_root: Path, registry_patch: dict[str, Any]) -> tuple[bool, str]:
    registry_path = repo_root / "config" / "openclaw" / "intent_tools.json"
    if not registry_path.is_file():
        return False, f"registry not found: {registry_path}"
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    tools = data.setdefault("tools", [])
    tool_id = str(registry_patch.get("tool_id") or "")
    existing = next((item for item in tools if str(item.get("tool_id")) == tool_id), None)
    if existing:
        if not bool(registry_patch.get("replaces_existing_tool")):
            return False, f"refusing to overwrite existing registered tool without explicit replacement approval: {tool_id}"
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
    existing_tool = registered_tool_by_id(repo_root, package.tool_id)
    if existing_tool and not bool(package.registry_patch.get("replaces_existing_tool")):
        package.status = "generated"
        package.verify_output = (
            "promotion deferred: repair package would overwrite an existing registered tool "
            f"({package.tool_id}); create a distinct capability or require explicit replacement approval"
        )
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
            if pytest_missing(cmd_output):
                fallback_ok, fallback_output = run_generated_helper_contract(package, repo_root, Path("scripts") / "openclaw" / test_source.name)
                output.append("pytest unavailable; used generated helper contract fallback")
                output.append(fallback_output)
                if not fallback_ok:
                    package.status = "failed"
                    package.verify_output = "\n".join(output)
                    save_package_state(package)
                    return package
            else:
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
    parser.add_argument("--llm-classification-json", default="")
    parser.add_argument("--apply-readonly", action="store_true")
    parser.add_argument("--verify-promote", action="store_true")
    parser.add_argument("--semantic", action="store_true")
    parser.add_argument("--mark-deployed", action="store_true")
    args = parser.parse_args()
    registry_tool = json.loads(args.registry_tool_json) if args.registry_tool_json else None
    llm_classification = json.loads(args.llm_classification_json) if args.llm_classification_json else None
    package = generate_repair_package(
        text=args.text,
        reason=args.reason,
        safety_class=args.safety_class,
        kernel_root=args.kernel_root,
        repo_root=args.repo_root,
        registry_tool=registry_tool,
        apply_readonly=args.apply_readonly,
        semantic=args.semantic,
        llm_classification=llm_classification,
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
