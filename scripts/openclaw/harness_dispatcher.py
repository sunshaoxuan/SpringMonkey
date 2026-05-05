#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from dm_capability_gap_runner import run_gap
from harness_context import build_context_bundle, context_to_prompt
from harness_governance import evaluate_tool_invocation
from harness_intent_agent import IntentFrame, infer_intent_frame
from harness_observability import EvaluationRecord, record_evaluation
from harness_reporter import ReportEnvelope, append_report, build_report, format_owner_reply
from harness_runtime import make_id
from harness_semantic_reviewer import SemanticReview, review_intent_frame
from harness_tool_binder import ToolBinding, bind_tool


@dataclass
class DispatchResult:
    status: str
    reply: str
    intent_frame: IntentFrame | None
    binding: ToolBinding | None
    review: SemanticReview | None
    args: dict[str, Any]
    returncode: int = 0
    route_kind: str = "unknown"
    report: ReportEnvelope | None = None
    context_summary: dict[str, Any] | None = None


Executor = Callable[[dict[str, Any], dict[str, Any], int], tuple[int, str]]
ArgExtractor = Callable[[dict[str, Any], str, str], dict[str, Any]]
ReplyFormatter = Callable[[dict[str, Any], dict[str, Any], int, str], str]
Auditor = Callable[..., Any]
Evaluator = Callable[[dict[str, Any], str, dict[str, Any]], Any]


def is_executor_capability_gap(output: str) -> bool:
    lowered = output.lower()
    return (
        "capability_gap" in lowered
        or "没有已验证" in output
        or "缺少已验证" in output
        or "missing verified" in lowered
        or "missing executor" in lowered
    )


def frame_reply(frame: IntentFrame) -> str:
    if frame.conversation_mode == "chat":
        return frame.canonical_text or frame.reason
    if frame.conversation_mode == "clarification":
        return frame.canonical_text or f"需要澄清：{frame.reason}"
    return f"未执行：{frame.reason}"


def handle_event(
    *,
    text: str,
    channel: str,
    user_id: str,
    message_timestamp: str,
    registry: dict[str, Any],
    context: str,
    kernel_root: Path,
    timeout_seconds: int,
    extract_args: ArgExtractor,
    run_tool: Executor,
    format_reply: ReplyFormatter,
    audit_intent: Auditor,
    evaluate_result: Evaluator,
    model_caller: Callable[[list[dict[str, str]]], str] | None = None,
) -> DispatchResult:
    trace_id = make_id("trace")
    task_id = make_id("task")
    context_bundle = build_context_bundle(
        trace_id=trace_id,
        intent="dm.event",
        channel=channel,
        user_id=user_id,
        dm_context=context,
        include_business_context=True,
        include_registry=True,
    )
    prompt_context = context_to_prompt(context_bundle)
    context_summary = {
        "trace_id": trace_id,
        "task_id": task_id,
        "dm_context": bool(context_bundle.dm_context),
        "business_context": bool(context_bundle.business_context),
        "registry_summary": bool(context_bundle.registry_summary),
    }

    def finish(
        status: str,
        summary: str,
        frame: IntentFrame | None,
        binding: ToolBinding | None,
        review: SemanticReview | None,
        args: dict[str, Any],
        returncode: int,
        route_kind: str,
        *,
        stage: str,
        tool: dict[str, Any] | None = None,
        visibility: str = "owner_dm",
        failure_type: str = "",
        public_payload: str = "",
    ) -> DispatchResult:
        report = build_report(
            task_id=task_id,
            trace_id=trace_id,
            status=status,
            stage=stage,
            summary=summary,
            route_kind=route_kind,
            tool=tool,
            visibility=visibility,
            failure_type=failure_type,
            public_payload=public_payload,
        )
        append_report(report)
        return DispatchResult(
            status,
            format_owner_reply(report),
            frame,
            binding,
            review,
            args,
            returncode,
            route_kind,
            report,
            context_summary,
        )

    try:
        frame = infer_intent_frame(text, context=prompt_context, registry=registry, model_caller=model_caller)
    except Exception as exc:
        reason = f"intent model unavailable or invalid: {type(exc).__name__}: {exc}"
        gap_result = run_gap(text=text, channel=channel, user_id=user_id, intent_reason=reason, kernel_root=kernel_root)
        return finish(
            "unsupported",
            "\n".join(["汤猴未执行该请求。", "原因：意图模型不可用或返回无效 IntentFrame。", f"记录：{gap_result.gap_ref}"]),
            None,
            None,
            None,
            {},
            0,
            "intent_model_unavailable",
            stage="intent",
            failure_type="intent_model_unavailable",
        )

    binding = bind_tool(frame, registry)
    if binding.status == "chat":
        return finish("chat", frame_reply(frame), frame, binding, None, {}, 0, "chat", stage="intent")
    if binding.status in {"clarification", "gap"} or not binding.tool:
        gap_result = run_gap(text=text, channel=channel, user_id=user_id, intent_reason=binding.reason, kernel_root=kernel_root)
        return finish(
            "unsupported",
            "\n".join([frame_reply(frame), f"记录：{gap_result.gap_ref}"]),
            frame,
            binding,
            None,
            {},
            0,
            binding.status,
            stage="binding",
            failure_type="tool_binding_gap",
        )

    review = review_intent_frame(frame, binding.tool, text)
    if not review.passed:
        gap_result = run_gap(text=text, channel=channel, user_id=user_id, intent_reason=f"{review.conflict_type}: {review.reason}", kernel_root=kernel_root)
        return finish(
            "unsupported",
            "\n".join(["汤猴已拦截语义冲突，未执行工具。", f"原因：{review.reason}", f"记录：{gap_result.gap_ref}"]),
            frame,
            binding,
            review,
            {},
            0,
            "intent_conflict",
            stage="semantic_review",
            tool=binding.tool,
            failure_type=review.conflict_type or "semantic_conflict",
        )

    args = extract_args(binding.tool, frame.canonical_text or text, message_timestamp)
    args["_model_intent_frame"] = asdict(frame)
    audit = audit_intent(text=args.get("text", frame.canonical_text or text), context=prompt_context, selected_tool=binding.tool, extracted_args=args)
    args = audit.corrected_args
    args["_result_contract"] = audit.result_contract
    args["_harness_trace_id"] = trace_id
    args["_harness_task_id"] = task_id
    decision = evaluate_tool_invocation(binding.tool, channel=channel, user_id=user_id)
    if not decision.allowed:
        return finish(
            "failed",
            "\n".join(["汤猴事件入口拒绝执行该工具。", f"工具：{binding.tool.get('tool_id')}", f"原因：{decision.reason}"]),
            frame,
            binding,
            review,
            args,
            1,
            "governance_denied",
            stage="governance",
            tool=binding.tool,
            visibility=decision.report_visibility,
            failure_type="governance_denied",
        )

    returncode, output = run_tool(binding.tool, args, timeout_seconds)
    if is_executor_capability_gap(output):
        gap_result = run_gap(
            text=text,
            channel=channel,
            user_id=user_id,
            intent_reason=f"registered tool executor capability gap: {output}",
            kernel_root=kernel_root,
            registry_tool=binding.tool,
        )
        return finish(
            "unsupported",
            "\n".join(["汤猴事件入口发现注册工具执行器能力缺口。", f"工具：{binding.tool.get('tool_id')}", f"记录：{gap_result.gap_ref}"]),
            frame,
            binding,
            review,
            args,
            returncode,
            "registered_tool_capability_gap",
            stage="execute",
            tool=binding.tool,
            visibility=decision.report_visibility,
            failure_type="executor_capability_gap",
        )
    evaluation = evaluate_result(binding.tool, output, audit.result_contract)
    record_evaluation(
        EvaluationRecord(
            trace_id=str(args.get("_harness_trace_id") or ""),
            evaluator_agent="evaluatorAgent",
            passed=bool(evaluation.passed),
            reason=str(evaluation.reason),
            result_contract=json.dumps(evaluation.result_contract, ensure_ascii=False, sort_keys=True),
            actual_result=json.dumps(evaluation.actual, ensure_ascii=False, sort_keys=True),
            gap_type=evaluation.gap_type or "",
        )
    )
    if returncode == 0 and not evaluation.passed:
        gap_result = run_gap(
            text=text,
            channel=channel,
            user_id=user_id,
            intent_reason=f"{evaluation.gap_type or 'result_evaluation_failed'}: {evaluation.reason}",
            kernel_root=kernel_root,
            forced_safety_class=evaluation.gap_type or "registered_tool_parameter_gap",
            forced_safety_reason=evaluation.reason,
            registry_tool=binding.tool,
        )
        return finish(
            "unsupported",
            "\n".join(["汤猴事件入口已拦截一次不满足契约的工具结果。", f"工具：{binding.tool.get('tool_id')}", f"原因：{evaluation.reason}", f"记录：{gap_result.gap_ref}"]),
            frame,
            binding,
            review,
            args,
            0,
            evaluation.gap_type or "result_evaluation_failed",
            stage="evaluate",
            tool=binding.tool,
            visibility=decision.report_visibility,
            failure_type=evaluation.gap_type or "result_contract_failed",
        )
    status = "ok" if returncode == 0 else "failed"
    failure_type = "" if returncode == 0 else "executor_failed"
    return finish(
        status,
        format_reply(binding.tool, args, returncode, output),
        frame,
        binding,
        review,
        args,
        returncode,
        "registered_task",
        stage="report" if returncode == 0 else "execute",
        tool=binding.tool,
        visibility=decision.report_visibility,
        failure_type=failure_type,
        public_payload=output if returncode == 0 else "",
    )
