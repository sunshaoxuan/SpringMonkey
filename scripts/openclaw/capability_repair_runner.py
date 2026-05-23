#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from dm_capability_gap_runner import GapRunnerResult, run_gap
from capability_blocker_classifier import CapabilityBlockerClassification, classify_capability_blocker, classification_dict
from domain_implementation_runner import DomainImplementationRun, start_implementation as start_domain_implementation
from regression_repair_runner import run_regression_repair
from toolsmith_repair_runner import ToolsmithPackage, append_package_log, generate_repair_package, mark_deployed, repair_fingerprint, save_package_state, verify_and_promote_package


DEFAULT_KERNEL_ROOT = Path("/var/lib/openclaw/.openclaw/workspace/agent_society_kernel")
REPLAYABLE_STAGES = {
    "intent",
    "binding",
    "semantic_review",
    "execute",
    "evaluate",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RepairRunnerResult:
    status: str
    stage: str
    safety_class: str
    gap_ref: str
    replay_allowed: bool
    replay_reason: str
    reply: str
    plan: dict[str, Any]
    registry_tool: dict[str, Any] | None = None
    toolsmith_package: dict[str, Any] | None = None
    implementation_run: dict[str, Any] | None = None
    event_log: str = ""
    created_at: str = ""


def event_log_path(kernel_root: Path) -> Path:
    return kernel_root / "capability_gap_events.jsonl"


def append_event(kernel_root: Path, payload: dict[str, Any]) -> Path:
    path = event_log_path(kernel_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def read_events(kernel_root: Path) -> list[dict[str, Any]]:
    path = event_log_path(kernel_root)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def upsert_event(kernel_root: Path, payload: dict[str, Any], fingerprint: str) -> Path:
    path = event_log_path(kernel_root)
    rows = read_events(kernel_root)
    replaced = False
    for index, row in enumerate(rows):
        if row.get("repair_fingerprint") == fingerprint:
            rows[index] = payload
            replaced = True
            break
    if not replaced:
        rows.append(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    return path


def regression_package_state_path(kernel_root: Path, package: dict[str, Any]) -> Path:
    package_id = str(package.get("package_id") or "regression_repair")
    path = kernel_root / "regression_packages" / package_id / "package_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "package_id": package_id,
        "status": package.get("status"),
        "gap_type": package.get("regression_type"),
        "safety_class": package.get("risk_level"),
        "tool_id": package.get("expected_tool_id"),
        "permission_scope": "owner_controlled_internal_repair",
        "write_operation": bool(package.get("write_operation")),
        "external_side_effect": bool(package.get("external_side_effect")),
        "internal_repair_allowed": bool(package.get("internal_repair_allowed")),
        "replay_policy": "blocked_until_domain_implementation",
        "reason": package.get("reason"),
        "files": [],
        "fingerprint": package.get("fingerprint"),
        "verify_command": package.get("verify_command"),
        "candidate_changes": package.get("candidate_changes"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def is_tool_readonly(tool: dict[str, Any] | None) -> bool:
    return bool(tool) and not bool(tool.get("write_operation"))


def replay_decision(
    *,
    stage: str,
    gap_result: GapRunnerResult,
    replay_depth: int,
    registry_tool: dict[str, Any] | None,
) -> tuple[bool, str]:
    if replay_depth > 0:
        return False, "已经尝试过一次受控重放"
    if stage not in REPLAYABLE_STAGES:
        return False, f"当前阶段 {stage} 不允许自动重放"
    if gap_result.status != "promoted":
        return False, f"修复状态为 {gap_result.status}，尚未提升为可重放能力"
    tool = registry_tool or gap_result.registry_tool
    if not is_tool_readonly(tool):
        return False, "候选修复不是已验证的只读工具"
    return True, "已验证的只读修复可重放一次"


def package_replay_decision(*, stage: str, package: ToolsmithPackage | None, replay_depth: int, require_deployed: bool = False) -> tuple[bool, str]:
    if replay_depth > 0:
        return False, "已经尝试过一次受控重放"
    if stage not in REPLAYABLE_STAGES:
        return False, f"当前阶段 {stage} 不允许自动重放"
    if package is None:
        return False, "没有可提升的修复包"
    if package.status not in {"promoted", "deployed"}:
        return False, f"修复包状态为 {package.status}，尚未提升"
    if require_deployed and package.status != "deployed":
        return False, "修复包已提升但尚未标记为已部署"
    if package.write_operation:
        return False, "修复包属于写入范围"
    return True, "已提升的只读修复包可重放一次"


def run_repair(
    *,
    text: str,
    channel: str,
    user_id: str,
    stage: str,
    reason: str,
    kernel_root: Path = DEFAULT_KERNEL_ROOT,
    repo_root: Path | None = None,
    execution_output: str = "",
    context: str = "",
    registry_tool: dict[str, Any] | None = None,
    forced_safety_class: str | None = None,
    forced_safety_reason: str | None = None,
    replay_depth: int = 0,
    semantic: bool = False,
    deploy_readonly: bool = False,
    blocker_model_caller: Any | None = None,
    write_intent: bool = False,
    implementation_starter: Any | None = None,
) -> RepairRunnerResult:
    repo_root = repo_root or Path(__file__).resolve().parents[2]
    regression = run_regression_repair(
        text=text,
        stage=stage,
        reason=reason,
        kernel_root=kernel_root,
        cases_path=repo_root / "config" / "openclaw" / "capability_baseline_cases.json",
        registry_path=repo_root / "config" / "openclaw" / "intent_tools.json",
    )
    if regression.matched:
        implementation_run: DomainImplementationRun | None = None
        status = regression.status
        replay_allowed = regression.status == "verified" and not regression.write_operation and replay_depth == 0
        replay_reason = (
            "已验证的只读基线回归可重放一次"
            if replay_allowed
            else ("写入能力回归已允许内部修复，真实外部写入仍需原始命令或明确重试" if regression.write_operation else f"回归修复状态为 {regression.status}")
        )
        if regression.write_operation:
            starter = implementation_starter or start_domain_implementation
            try:
                package_state = regression_package_state_path(kernel_root, regression.package)
                implementation_run = starter(
                    package_state=package_state,
                    text=text,
                    reason=reason,
                    repo_root=repo_root,
                    kernel_root=kernel_root,
                )
                status = "repair_started" if implementation_run.status == "running" else "final_failed"
                replay_reason = (
                    f"已启动内部回归修复 run={implementation_run.run_id}，外部写入重放仍受策略门控"
                    if status == "repair_started"
                    else f"内部回归修复启动失败：{implementation_run.evidence}"
                )
            except Exception as exc:
                status = "final_failed"
                replay_reason = f"内部回归修复启动异常：{type(exc).__name__}: {exc}"
        event = {
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "repair_fingerprint": regression.fingerprint,
            "text": text,
            "channel": channel,
            "user_id": user_id,
            "stage": stage,
            "reason": reason,
            "execution_output_tail": execution_output[-2000:],
            "context_tail": context[-2000:],
            "gap_ref": f"regression_ref={regression.package.get('package_id')}",
            "gap_status": "regression",
            "runner_status": status,
            "safety_class": "requires_confirmation_or_credentials" if regression.write_operation else "auto_safe_readonly",
            "replay_allowed": replay_allowed,
            "replay_reason": replay_reason,
            "tool_id": regression.expected_tool_id,
            "regression_ref": regression.package.get("package_id"),
            "baseline_case_id": regression.baseline_case_id,
            "expected_tool_id": regression.expected_tool_id,
            "actual_stage": regression.actual_stage,
            "repair_status": status,
            "regression_type": regression.regression_type,
            "match_kind": regression.match_kind,
            "reference_tools": regression.reference_tools or [],
            "plan": {
                "gap_id": regression.package.get("package_id"),
                "summary": (
                    f"Known-direction capability repair: {regression.baseline_case_id}"
                    if regression.match_kind == "capability_family"
                    else f"Existing baseline capability regression: {regression.baseline_case_id}"
                ),
                "next_required_change": regression.package.get("candidate_changes", []),
                "verify_command": regression.package.get("verify_command"),
            },
            "resolved_by": {
                "package_id": regression.package.get("package_id"),
                "status": regression.status,
                "gap_type": regression.regression_type,
                "tool_id": regression.expected_tool_id,
                "replay_policy": "external_replay_gated_after_internal_repair" if regression.write_operation else "verify_before_replay",
                "verify_output_tail": regression.package.get("baseline_result", {}).get("reason", ""),
                "promoted_at": utc_now() if replay_allowed else "",
                "deployment_status": "internal_repair_started" if implementation_run else ("not_requested" if not regression.write_operation else "internal_repair_required"),
                "implementation_run": None if implementation_run is None else asdict(implementation_run),
            },
        }
        log_path = upsert_event(kernel_root, event, regression.fingerprint)
        reply = "\n".join(
            [
                "汤猴识别到这是既有能力回归，不是新工具缺口。",
                f"baseline_case={regression.baseline_case_id}",
                f"expected_tool={regression.expected_tool_id}",
                f"regression_type={regression.regression_type}",
                f"match_kind={regression.match_kind}",
                f"修复包状态：{status}",
                f"重放判定：{'允许' if replay_allowed else '不允许'}，{replay_reason}",
                f"事件日志：{log_path}",
            ]
        )
        return RepairRunnerResult(
            status=status,
            stage=stage,
            safety_class="requires_confirmation_or_credentials" if regression.write_operation else "auto_safe_readonly",
            gap_ref=f"regression_ref={regression.package.get('package_id')}",
            replay_allowed=replay_allowed,
            replay_reason=replay_reason,
            reply=reply,
            plan=event["plan"],
            registry_tool=registry_tool,
            toolsmith_package=regression.package,
            implementation_run=None if implementation_run is None else asdict(implementation_run),
            event_log=str(log_path),
            created_at=utc_now(),
        )
    blocker: CapabilityBlockerClassification | None = None
    if forced_safety_class is None:
        blocker = classify_capability_blocker(
            text=text,
            stage=stage,
            reason=reason,
            execution_output=execution_output,
            context=context,
            repo_root=repo_root,
            model_caller=blocker_model_caller,
        )
        if blocker.autonomy_allowed:
            forced_safety_class = "auto_safe_readonly"
            forced_safety_reason = blocker.reasoning_summary
        elif blocker.blocker_kind == "registered_tool_regression":
            forced_safety_class = "unsupported_or_ambiguous"
            forced_safety_reason = "LLM classified this as registered_tool_regression but no baseline case matched; human review required"
        else:
            forced_safety_class = blocker.safety_class
            forced_safety_reason = blocker.reasoning_summary
        if write_intent and blocker.autonomy_allowed and blocker.blocker_kind not in {
            "access_or_approval_blocker",
            "credential_missing",
            "ambiguous",
            "write_operation_request",
        }:
            blocker.blocker_kind = "write_operation_request"
            blocker.replay_policy = "blocked_until_human_review"
            blocker.reasoning_summary = (
                f"{blocker.reasoning_summary} IntentFrame safety=write; route as an implementation plan, "
                "not as a generic read-only helper."
            )

    intent_reason = reason
    if execution_output:
        intent_reason = f"{intent_reason}; output={execution_output[:1200]}"
    gap_result = run_gap(
        text=text,
        channel=channel,
        user_id=user_id,
        intent_reason=intent_reason,
        kernel_root=kernel_root,
        repo_root=repo_root,
        forced_safety_class=forced_safety_class,
        forced_safety_reason=forced_safety_reason,
        registry_tool=registry_tool,
    )
    replay_allowed, replay_reason = replay_decision(
        stage=stage,
        gap_result=gap_result,
        replay_depth=replay_depth,
        registry_tool=registry_tool,
    )
    status = gap_result.status
    toolsmith_package: ToolsmithPackage | None = None
    implementation_run: DomainImplementationRun | None = None
    if replay_allowed:
        status = "verified"
    elif gap_result.status == "blocked":
        status = "blocked"
    elif gap_result.status == "planned":
        status = "planned"
    if not replay_allowed:
        autonomous_semantic = bool(blocker and blocker.autonomy_allowed)
        toolsmith_package = generate_repair_package(
            text=text,
            reason=reason,
            safety_class=gap_result.safety_class,
            kernel_root=kernel_root,
            repo_root=repo_root,
            registry_tool=registry_tool or gap_result.registry_tool,
            apply_readonly=False,
            semantic=semantic or deploy_readonly or autonomous_semantic,
            llm_classification=classification_dict(blocker),
        )
        if toolsmith_package.status == "generated" and toolsmith_package.safety_class == "auto_safe_readonly":
            toolsmith_package = verify_and_promote_package(toolsmith_package, kernel_root=kernel_root, repo_root=repo_root)
        if deploy_readonly and toolsmith_package.status == "promoted" and not toolsmith_package.write_operation:
            toolsmith_package = mark_deployed(toolsmith_package)
        append_package_log(kernel_root, toolsmith_package)
        package_replay_allowed, package_replay_reason = package_replay_decision(
            stage=stage,
            package=toolsmith_package,
            replay_depth=replay_depth,
            require_deployed=deploy_readonly,
        )
        if blocker and blocker.blocker_kind == "write_operation_request":
            package_replay_allowed = False
            package_replay_reason = "写入型请求可以先生成内部修复路线，但原任务重放需要通过策略批准"
        if package_replay_allowed:
            replay_allowed = True
            replay_reason = package_replay_reason
            status = toolsmith_package.status
        elif (
            toolsmith_package.status == "planned"
            and toolsmith_package.replay_policy == "blocked_until_domain_implementation"
            and blocker
            and blocker.autonomy_allowed
        ):
            starter = implementation_starter or start_domain_implementation
            try:
                implementation_run = starter(
                    package_state=Path(toolsmith_package.package_dir) / "package_state.json",
                    text=text,
                    reason=reason,
                    repo_root=repo_root,
                    kernel_root=kernel_root,
                )
                toolsmith_package.deployment_status = (
                    "implementation_started"
                    if implementation_run.status == "running"
                    else f"implementation_{implementation_run.status}"
                )
                toolsmith_package.verify_output = (
                    f"domain implementation run {implementation_run.run_id}: "
                    f"{implementation_run.status}/{implementation_run.stage}; {implementation_run.evidence}"
                )
                save_package_state(toolsmith_package)
                status = "repair_started" if implementation_run.status == "running" else "failed"
                replay_reason = (
                    f"已启动内部能力实现 run={implementation_run.run_id}，完成验证前不重放原任务"
                    if status == "repair_started"
                    else f"内部能力实现启动失败：{implementation_run.evidence}"
                )
            except Exception as exc:
                status = "failed"
                replay_reason = f"内部能力实现启动异常：{type(exc).__name__}: {exc}"
        elif toolsmith_package.status in {"planned", "generated", "verified", "promoted", "deployed", "failed"}:
            status = toolsmith_package.status
        elif toolsmith_package.status == "blocked_requires_authorization":
            status = "blocked"
    effective_tool = registry_tool or gap_result.registry_tool or (toolsmith_package.registry_patch if toolsmith_package and toolsmith_package.status == "promoted" else None)
    fingerprint = ""
    if toolsmith_package:
        fingerprint = toolsmith_package.fingerprint
    else:
        tool_id = str((effective_tool or {}).get("tool_id") or "")
        entrypoint = str((effective_tool or {}).get("entrypoint") or "")
        fingerprint = repair_fingerprint(text=text, reason=reason, tool_id=tool_id, entrypoint=entrypoint)
    event = {
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "repair_fingerprint": fingerprint,
        "text": text,
        "channel": channel,
        "user_id": user_id,
        "stage": stage,
        "reason": reason,
        "execution_output_tail": execution_output[-2000:],
        "context_tail": context[-2000:],
        "gap_ref": gap_result.gap_ref,
        "gap_status": gap_result.status,
        "runner_status": status,
        "safety_class": gap_result.safety_class,
        "replay_allowed": replay_allowed,
        "replay_reason": replay_reason,
        "tool_id": (effective_tool or {}).get("tool_id"),
        "llm_intent_kind": blocker.intent_kind if blocker else "",
        "llm_blocker_kind": blocker.blocker_kind if blocker else "",
        "llm_confidence": blocker.confidence if blocker else None,
        "missing_condition": blocker.missing_condition if blocker else "",
        "allowed_repair_action": blocker.allowed_repair_action if blocker else "",
        "autonomy_allowed": blocker.autonomy_allowed if blocker else None,
        "autonomy_boundary": blocker.autonomy_boundary if blocker else "",
        "llm_classification_ok": blocker.ok if blocker else None,
        "llm_classification_error": blocker.error if blocker else "",
        "plan": asdict(gap_result.plan),
        "resolved_by": None if toolsmith_package is None else {
            "package_id": toolsmith_package.package_id,
            "status": toolsmith_package.status,
            "gap_type": toolsmith_package.gap_type,
            "tool_id": toolsmith_package.tool_id,
            "replay_policy": toolsmith_package.replay_policy,
            "verify_output_tail": toolsmith_package.verify_output[-2000:],
            "promoted_at": toolsmith_package.promoted_at,
            "deployment_status": toolsmith_package.deployment_status,
            "implementation_run": None if implementation_run is None else asdict(implementation_run),
        },
    }
    log_path = upsert_event(kernel_root, event, fingerprint)
    reply = "\n".join(
        [
            gap_result.reply,
            f"自演进状态：{status}",
            f"重放判定：{'允许' if replay_allowed else '不允许'}，{replay_reason}",
            f"工具匠：{toolsmith_package.status if toolsmith_package else 'not_needed'}",
            f"实现任务：{implementation_run.run_id if implementation_run else 'not_started'}",
            f"事件日志：{log_path}",
        ]
    )
    return RepairRunnerResult(
        status=status,
        stage=stage,
        safety_class=gap_result.safety_class,
        gap_ref=gap_result.gap_ref,
        replay_allowed=replay_allowed,
        replay_reason=replay_reason,
        reply=reply,
        plan=asdict(gap_result.plan),
        registry_tool=effective_tool,
        toolsmith_package=None if toolsmith_package is None else asdict(toolsmith_package),
        implementation_run=None if implementation_run is None else asdict(implementation_run),
        event_log=str(log_path),
        created_at=event["created_at"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Record and repair OpenClaw capability gaps through one bounded loop.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--channel", default="discord_dm")
    parser.add_argument("--user-id", default="unknown")
    parser.add_argument("--stage", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--execution-output", default="")
    parser.add_argument("--context", default="")
    parser.add_argument("--kernel-root", type=Path, default=DEFAULT_KERNEL_ROOT)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--replay-depth", type=int, default=0)
    parser.add_argument("--semantic", action="store_true")
    parser.add_argument("--deploy-readonly", action="store_true")
    parser.add_argument("--known-direction", action="store_true", help="Compatibility flag: baseline/family repair is always attempted before generic gaps.")
    args = parser.parse_args()
    result = run_repair(
        text=args.text,
        channel=args.channel,
        user_id=args.user_id,
        stage=args.stage,
        reason=args.reason,
        execution_output=args.execution_output,
        context=args.context,
        kernel_root=args.kernel_root,
        repo_root=args.repo_root,
        replay_depth=args.replay_depth,
        semantic=args.semantic,
        deploy_readonly=args.deploy_readonly,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.status in {"recorded", "planned", "generated", "verified", "promoted", "deployed", "replayed", "repair_started", "final_succeeded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
