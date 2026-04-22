#!/usr/bin/env python3
from __future__ import annotations

import re


CASUAL_PATTERN = re.compile(
    r"^\s*(你好|您好|hi|hello|早上好|晚上好|谢谢|thanks|ok|好的|收到|嗯|在吗|拜拜|bye)[!！,.，。 ]*\s*$",
    re.IGNORECASE,
)

TRIVIAL_PATTERN = re.compile(
    r"(几点|时间|time\b|天气$|weather$|你是谁|who are you)",
    re.IGNORECASE,
)

REQUEST_SIGNAL_PATTERN = re.compile(
    r"(请你|帮我|麻烦你|拜托|需要你|去帮|请帮|请处理|帮忙|看看|查一下|调查一下|排查一下|修一下|跟进一下|安排一下)",
    re.IGNORECASE,
)

EXECUTION_SIGNAL_PATTERN = re.compile(
    r"(处理|执行|完成|安排|调查|排查|修复|检查|查找|验证|测试|监视|盯住|跟进|整理|总结|汇报|报告|同步|通知|提醒|创建|生成|配置|设置|部署|重启|登录|改密码|保存密码|发到|转发|重跑|跑一下|确认一下)",
    re.IGNORECASE,
)

OPERATION_VERB_PATTERN = re.compile(
    r"(登录|登入|log\s?in|sign\s?in|change\s+password|reset\s+password|修改密码|重置密码|打开|访问|进入|navigate|open|visit|click|点击|search|查找|设置|配置|保存密码|提交|上传|download|upload|修复|排查|测试)",
    re.IGNORECASE,
)

OPERATION_TARGET_PATTERN = re.compile(
    r"(邮箱|email|mail|账号|account|网站|网页|browser|登录页|设置页|password|密码|google|docs|小红书|line|discord|slack|notion|service|系统|portal|dashboard)",
    re.IGNORECASE,
)

TASKING_SIGNAL_PATTERN = re.compile(
    r"(并|然后|再|同时|顺便|继续|并且|此外|还要|以及|总结|汇报|报告|验证|记录|记住|remember|report|verify|save|continue|follow\s?up|status)",
    re.IGNORECASE,
)

REPAIR_SIGNAL_PATTERN = re.compile(
    r"(修复|排查|失败|卡住|超时|timeout|drift|锚点|工具|script|helper|自动化|记住方法|self\s?repair|toolsmith)",
    re.IGNORECASE,
)


def normalize_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt or "").strip()


def should_apply_operational_execution_protocol(prompt: str, *, is_direct: bool = True, is_heartbeat: bool = False) -> bool:
    if is_heartbeat or not is_direct:
        return False
    text = normalize_prompt(prompt)
    if not text:
        return False
    return bool(OPERATION_VERB_PATTERN.search(text) and OPERATION_TARGET_PATTERN.search(text))


def should_apply_agent_society_protocol(prompt: str, *, is_direct: bool = True, is_heartbeat: bool = False) -> bool:
    if is_heartbeat or not is_direct:
        return False
    text = normalize_prompt(prompt)
    if not text or CASUAL_PATTERN.fullmatch(text):
        return False
    if TRIVIAL_PATTERN.search(text) and not REQUEST_SIGNAL_PATTERN.search(text) and not EXECUTION_SIGNAL_PATTERN.search(text):
        return False
    if should_apply_operational_execution_protocol(text, is_direct=is_direct, is_heartbeat=is_heartbeat):
        return True
    if REQUEST_SIGNAL_PATTERN.search(text) and EXECUTION_SIGNAL_PATTERN.search(text):
        return True
    if EXECUTION_SIGNAL_PATTERN.search(text) and (TASKING_SIGNAL_PATTERN.search(text) or len(text) >= 18):
        return True
    return False


def should_apply_self_improvement_protocol(prompt: str, *, is_direct: bool = True, is_heartbeat: bool = False) -> bool:
    if not should_apply_agent_society_protocol(prompt, is_direct=is_direct, is_heartbeat=is_heartbeat):
        return False
    text = normalize_prompt(prompt)
    return bool(REPAIR_SIGNAL_PATTERN.search(text) or should_apply_operational_execution_protocol(text, is_direct=is_direct, is_heartbeat=is_heartbeat))


__all__ = [
    "normalize_prompt",
    "should_apply_agent_society_protocol",
    "should_apply_operational_execution_protocol",
    "should_apply_self_improvement_protocol",
]
