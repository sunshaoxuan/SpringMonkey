#!/usr/bin/env python3
from __future__ import annotations

from agent_society_entry_policy import (
    AGENTIC_DEPTH,
    CHAT_KIND,
    STAGED_DEPTH,
    TASK_KIND,
    build_multistep_task_protocol,
    classify_execution_depth,
    classify_interaction_kind,
    should_apply_agent_society_protocol,
    should_apply_operational_execution_protocol,
    should_apply_self_improvement_protocol,
)


POSITIVE_AGENT_SOCIETY = [
    "请你处理你自己的邮箱事务，登录后改密码并向我汇报状态。",
    "看看今天 Discord 新闻任务为什么失败，排查完修好再告诉我。",
    "帮我创建一个每天 7 点发到 Discord 的天气提醒，并验证是否成功。",
]

NEGATIVE_AGENT_SOCIETY = [
    "你好",
    "现在几点了",
    "谢谢",
]

POSITIVE_OPERATIONAL = [
    "请你登录你自己的邮箱并修改密码。",
    "打开 Discord 设置页检查当前账号状态。",
]

POSITIVE_SELF_IMPROVEMENT = [
    "排查这个任务为什么卡住并修复超时问题。",
    "修复 bundle drift，必要时写 helper script。",
]

STAGED_DEPTH_PROMPTS = [
    "请你每天早上抓取天气，翻译成中文，整理成报告后发到 Discord。",
    "帮我登录网站查询预约状态并汇报结果。",
]

AGENTIC_DEPTH_PROMPTS = [
    "你要自己分辨是聊天还是任务，如果是任务就要创建多步式任务，然后自己写工具并调试上线新工具。",
    "自己判断怎么拆解任务，动态重规划，必要时写工具并持续增强自己的能力。",
]


def main() -> int:
    for prompt in POSITIVE_AGENT_SOCIETY:
        if not should_apply_agent_society_protocol(prompt):
            raise AssertionError(f"expected agent-society attach for: {prompt}")
    for prompt in NEGATIVE_AGENT_SOCIETY:
        if should_apply_agent_society_protocol(prompt):
            raise AssertionError(f"did not expect agent-society attach for: {prompt}")
        if classify_interaction_kind(prompt) != CHAT_KIND:
            raise AssertionError(f"expected chat classification for: {prompt}")
    for prompt in POSITIVE_OPERATIONAL:
        if not should_apply_operational_execution_protocol(prompt):
            raise AssertionError(f"expected operational attach for: {prompt}")
    for prompt in POSITIVE_SELF_IMPROVEMENT:
        if not should_apply_self_improvement_protocol(prompt):
            raise AssertionError(f"expected self-improvement attach for: {prompt}")
    for prompt in POSITIVE_AGENT_SOCIETY:
        if classify_interaction_kind(prompt) != TASK_KIND:
            raise AssertionError(f"expected task classification for: {prompt}")
    for prompt in STAGED_DEPTH_PROMPTS:
        if classify_execution_depth(prompt) != STAGED_DEPTH:
            raise AssertionError(f"expected staged depth for: {prompt}")
        protocol = build_multistep_task_protocol(prompt)
        if "execution_depth: staged" not in protocol:
            raise AssertionError(f"expected staged protocol for: {prompt}")
    for prompt in AGENTIC_DEPTH_PROMPTS:
        if classify_execution_depth(prompt) != AGENTIC_DEPTH:
            raise AssertionError(f"expected agentic depth for: {prompt}")
        protocol = build_multistep_task_protocol(prompt)
        if "execution_depth: agentic" not in protocol or "create it, debug it, validate it" not in protocol:
            raise AssertionError(f"expected agentic protocol for: {prompt}")
    print("agent_society_entry_policy_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
