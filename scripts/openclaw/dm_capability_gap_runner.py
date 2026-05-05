#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from agent_society_kernel import AgentSocietyKernel


REPO = Path(__file__).resolve().parents[2]
DEFAULT_KERNEL_ROOT = Path("/var/lib/openclaw/.openclaw/workspace/agent_society_kernel")

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


@dataclass
class CapabilityPlan:
    capability_id: str
    source_gap_id: str
    safety_class: str
    tool_id: str | None
    entrypoint: str | None
    registry_patch: dict[str, Any] | None
    verify_commands: list[str]
    replay_text: str
    status: str
    reason: str


@dataclass
class GapRunnerResult:
    status: str
    safety_class: str
    plan: CapabilityPlan
    gap_ref: str
    reply: str
    registry_tool: dict[str, Any] | None = None


AUTO_SAFE_READONLY_RE = re.compile(
    r"(天气|天気|weather|预报|予報|风况|風|能见度|視程|可視性|节假日|祝日|红日子|赤い日|holiday)",
    re.IGNORECASE,
)

UNSAFE_RE = re.compile(
    r"(取消|修改|改|调整|设置|配置|部署|重启|删除|提交|支付|付款|订车|预约|timescar|密码|token|secret|key|密钥|登录|登入)",
    re.IGNORECASE,
)


WEATHER_DM_QUERY_TOOL = {
    "intent_id": "weather.dm.query",
    "tool_id": "weather.dm.query",
    "description": "Answer owner DM ad hoc weather queries with forecast, wind, and visibility.",
    "patterns": ["天气", "天気", "weather", "风", "風", "能见度", "視程", "可視性"],
    "required_any": ["明天", "后天", "今天", "预报", "查询", "看看", "东京", "東京", "长野", "長野"],
    "entrypoint": "scripts/weather/handle_dm_weather_query.py",
    "args_schema": {"mode": "dm_text_timestamp", "force": False},
    "permission": "owner_dm",
    "write_operation": False,
    "verify_command": "python -m compileall -q scripts/weather/handle_dm_weather_query.py && python scripts/weather/test_handle_dm_weather_query.py",
    "failure_policy": "reply_failure_and_record_gap",
    "reply_policy": "tool_stdout",
    "promotion": {
        "source": "agent_society_dm_gap_runner",
        "safety_class": "auto_safe_readonly",
        "status": "promoted_sample",
    },
}


TIMESCAR_CANCEL_PROMOTION_TOOL = {
    "intent_id": "timescar.reservation_cancel",
    "tool_id": "timescar.dm.cancel_next",
    "description": "Cancel the next TimesCar reservation from owner DM through a verified deterministic browser submitter.",
    "patterns": ["订车", "预约", "这单", "订单", "TimesCar", "timescar"],
    "required_any": ["取消这单", "取消订单", "取消预约", "取消订车", "cancel"],
    "entrypoint": "scripts/timescar/timescar_cancel_reservation.py",
    "args_schema": {"mode": "dm_text_timestamp", "force": True},
    "permission": "owner_dm_write",
    "write_operation": True,
    "confirm_policy": "deterministic_tool_with_confirm_page_and_postcheck",
    "idempotency": "target_booking_absent_after_success",
    "verify_command": (
        "python -m compileall -q scripts/timescar/timescar_handle_dm_adjust_request.py "
        "scripts/timescar/timescar_cancel_reservation.py && "
        "python scripts/timescar/test_timescar_dm_keep_cancel.py && "
        "python scripts/timescar/test_timescar_cancel_reservation.py"
    ),
    "failure_policy": "reply_failure_and_record_gap",
    "reply_policy": "tool_stdout",
    "promotion": {
        "source": "agent_society_dm_gap_runner",
        "safety_class": "requires_confirmation_or_credentials",
        "status": "requires_verified_git_delivery_before_replay",
    },
}


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def classify_safety(text: str, intent_reason: str = "") -> tuple[str, str]:
    combined = normalize(f"{text} {intent_reason}")
    if UNSAFE_RE.search(combined):
        return "requires_confirmation_or_credentials", "contains write, credential, booking, or configuration wording"
    if AUTO_SAFE_READONLY_RE.search(combined):
        return "auto_safe_readonly", "public read-only query wording"
    return "unsupported_or_ambiguous", "no registered safe auto-promotion pattern"


def promoted_tool_for_text(text: str) -> dict[str, Any] | None:
    if re.search(r"(天气|天気|weather|风况|風|能见度|視程|可視性)", text, re.IGNORECASE):
        return dict(WEATHER_DM_QUERY_TOOL)
    return None


def planned_tool_for_unsafe_text(text: str, intent_reason: str = "") -> dict[str, Any] | None:
    combined = f"{text} {intent_reason}"
    if re.search(r"(TimesCar|timescar|订车|预约|订单|这单)", combined, re.IGNORECASE) and re.search(
        r"(取消这单|取消订单|取消预约|取消订车|cancel)", combined, re.IGNORECASE
    ):
        return dict(TIMESCAR_CANCEL_PROMOTION_TOOL)
    return None


def run_verify_command(command: str, repo_root: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        command,
        cwd=repo_root,
        shell=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180,
    )
    return proc.returncode == 0, (proc.stdout or "").strip()


def record_kernel_gap(*, text: str, channel: str, user_id: str, observation: str, kernel_root: Path) -> tuple[str, str]:
    kernel = AgentSocietyKernel(kernel_root)
    session = kernel.bootstrap_session(text, channel=channel, user_id=user_id)
    step = kernel.next_step(session)
    if step is None:
        raise RuntimeError("agent society kernel did not create a step")
    kernel.record_observation(
        session,
        step.step_id,
        observation,
        "classify DM capability gap and decide whether safe auto-promotion is allowed",
        "blocked",
    )
    session = kernel.load_session(session.session_id)
    gap = kernel.analyze_capability_gap(session, step.step_id, observation)
    return session.session_id, gap.gap_id


def append_plan(kernel_root: Path, plan: CapabilityPlan) -> Path:
    path = kernel_root / "dm_capability_plans.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(plan), ensure_ascii=False) + "\n")
    return path


def build_plan(
    *,
    text: str,
    safety_class: str,
    reason: str,
    gap_id: str,
    registry_tool: dict[str, Any] | None,
) -> CapabilityPlan:
    verify_commands: list[str] = []
    entrypoint = None
    tool_id = None
    if registry_tool:
        tool_id = str(registry_tool["tool_id"])
        entrypoint = str(registry_tool["entrypoint"])
        verify = str(registry_tool.get("verify_command") or "").strip()
        if verify:
            verify_commands.append(verify)
    return CapabilityPlan(
        capability_id=f"capability_{gap_id.replace('gap_', '')}",
        source_gap_id=gap_id,
        safety_class=safety_class,
        tool_id=tool_id,
        entrypoint=entrypoint,
        registry_patch=registry_tool,
        verify_commands=verify_commands,
        replay_text=text,
        status="planned",
        reason=reason,
    )


def run_gap(
    *,
    text: str,
    channel: str,
    user_id: str,
    intent_reason: str,
    kernel_root: Path = DEFAULT_KERNEL_ROOT,
    repo_root: Path = REPO,
    forced_safety_class: str | None = None,
    forced_safety_reason: str | None = None,
    registry_tool: dict[str, Any] | None = None,
) -> GapRunnerResult:
    if forced_safety_class:
        safety_class = forced_safety_class
        safety_reason = forced_safety_reason or "forced by harness evaluator"
    else:
        safety_class, safety_reason = classify_safety(text, intent_reason)
    observation = f"dm intent tool router miss: {intent_reason}; safety={safety_class}; reason={safety_reason}"
    session_id, gap_id = record_kernel_gap(
        text=text,
        channel=channel,
        user_id=user_id,
        observation=observation,
        kernel_root=kernel_root,
    )
    registry_tool = registry_tool or (
        promoted_tool_for_text(text)
        if safety_class == "auto_safe_readonly"
        else planned_tool_for_unsafe_text(text, intent_reason)
    )
    plan = build_plan(
        text=text,
        safety_class=safety_class,
        reason=safety_reason,
        gap_id=gap_id,
        registry_tool=registry_tool,
    )
    plan_path = append_plan(kernel_root, plan)
    gap_ref = f"kernel_session={session_id} gap_id={gap_id} plan_log={plan_path}"

    if safety_class == "registered_tool_parameter_gap" and registry_tool and not bool(registry_tool.get("write_operation")):
        plan.status = "promoted_replay_ready"
        append_plan(kernel_root, plan)
        return GapRunnerResult(
            "promoted",
            safety_class,
            plan,
            gap_ref,
            f"已记录已注册只读工具的参数补强缺口，准备重放原始任务。记录：{gap_ref}",
            registry_tool,
        )

    if safety_class != "auto_safe_readonly":
        plan.status = "blocked_requires_human_or_registered_tool"
        append_plan(kernel_root, plan)
        reply = "\n".join(
            [
                "汤猴已收到私信，但该能力不能自动执行。",
                f"状态：未执行，已记录能力缺口和补强计划。",
                f"安全分类：{safety_class}",
                f"原因：{safety_reason}",
                f"候选工具：{registry_tool.get('tool_id') if registry_tool else '未生成'}",
                f"候选入口：{registry_tool.get('entrypoint') if registry_tool else '未生成'}",
                f"记录：{gap_ref}",
            ]
        )
        return GapRunnerResult("blocked", safety_class, plan, gap_ref, reply, registry_tool)

    if registry_tool is None:
        plan.status = "planned_no_known_promoter"
        append_plan(kernel_root, plan)
        reply = "\n".join(
            [
                "汤猴已收到只读请求，但没有找到可自动推广的确定性工具模板。",
                "状态：未执行，已记录能力缺口和候选补强计划。",
                f"记录：{gap_ref}",
            ]
        )
        return GapRunnerResult("planned", safety_class, plan, gap_ref, reply, None)

    verify_output: list[str] = []
    for command in plan.verify_commands:
        ok, output = run_verify_command(command, repo_root)
        verify_output.append(f"$ {command}\n{output or 'ok'}")
        if not ok:
            plan.status = "verify_failed"
            append_plan(kernel_root, plan)
            reply = "\n".join(
                [
                    "汤猴已生成只读能力补强计划，但验证未通过。",
                    "状态：未执行原任务。",
                    f"记录：{gap_ref}",
                    verify_output[-1],
                ]
            )
            return GapRunnerResult("failed", safety_class, plan, gap_ref, reply, registry_tool)

    plan.status = "promoted_replay_ready"
    append_plan(kernel_root, plan)
    return GapRunnerResult(
        "promoted",
        safety_class,
        plan,
        gap_ref,
        f"已生成并验证只读能力补强计划，准备重放原始任务。记录：{gap_ref}",
        registry_tool,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--intent-reason", default="")
    parser.add_argument("--kernel-root", type=Path, default=DEFAULT_KERNEL_ROOT)
    parser.add_argument("--repo-root", type=Path, default=REPO)
    args = parser.parse_args()
    result = run_gap(
        text=args.text,
        channel=args.channel,
        user_id=args.user_id,
        intent_reason=args.intent_reason,
        kernel_root=args.kernel_root,
        repo_root=args.repo_root,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.status in {"promoted", "blocked", "planned"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
