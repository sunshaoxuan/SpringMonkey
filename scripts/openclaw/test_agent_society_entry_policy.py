#!/usr/bin/env python3
from __future__ import annotations

from agent_society_entry_policy import (
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


def main() -> int:
    for prompt in POSITIVE_AGENT_SOCIETY:
        if not should_apply_agent_society_protocol(prompt):
            raise AssertionError(f"expected agent-society attach for: {prompt}")
    for prompt in NEGATIVE_AGENT_SOCIETY:
        if should_apply_agent_society_protocol(prompt):
            raise AssertionError(f"did not expect agent-society attach for: {prompt}")
    for prompt in POSITIVE_OPERATIONAL:
        if not should_apply_operational_execution_protocol(prompt):
            raise AssertionError(f"expected operational attach for: {prompt}")
    for prompt in POSITIVE_SELF_IMPROVEMENT:
        if not should_apply_self_improvement_protocol(prompt):
            raise AssertionError(f"expected self-improvement attach for: {prompt}")
    print("agent_society_entry_policy_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
