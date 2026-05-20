#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from contextlib import contextmanager

from agent_society_entry_policy import (
    AGENTIC_DEPTH,
    ATOMIC_DEPTH,
    CHAT_KIND,
    STAGED_DEPTH,
    TASK_KIND,
    build_entry_policy_prompt,
    build_multistep_task_protocol,
    classify_entry_policy,
    classify_execution_depth,
    classify_interaction_kind,
    should_apply_agent_society_protocol,
    should_apply_operational_execution_protocol,
    should_apply_self_improvement_protocol,
)


@contextmanager
def entry_frame(frame: dict):
    old = os.environ.get("OPENCLAW_ENTRY_POLICY_FRAME_JSON")
    os.environ["OPENCLAW_ENTRY_POLICY_FRAME_JSON"] = json.dumps(frame, ensure_ascii=False)
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("OPENCLAW_ENTRY_POLICY_FRAME_JSON", None)
        else:
            os.environ["OPENCLAW_ENTRY_POLICY_FRAME_JSON"] = old


def frame(
    *,
    kind: str = TASK_KIND,
    depth: str = STAGED_DEPTH,
    agent_society: bool = True,
    operational: bool = True,
    self_improvement: bool = False,
) -> dict:
    return {
        "interaction_kind": kind,
        "execution_depth": depth,
        "apply_agent_society": agent_society,
        "apply_operational_execution": operational,
        "apply_self_improvement": self_improvement,
        "reasoning_summary": "test semantic frame",
    }


def test_entry_policy_prompt_states_semantic_routing_law() -> None:
    messages = build_entry_policy_prompt("请处理这个问题", is_direct=True, is_heartbeat=False)
    combined = "\n".join(item["content"] for item in messages)

    assert "semantic classifier" in combined
    assert "Do not use keyword matching, regex matching" in combined
    assert "Use meaning, user goal" in combined


def test_simple_chat_branch_is_the_only_non_model_shortcut() -> None:
    assert classify_interaction_kind("你好") == CHAT_KIND
    assert not should_apply_agent_society_protocol("谢谢")


def test_model_frame_controls_task_classification_not_keywords() -> None:
    with entry_frame(frame(kind=TASK_KIND, depth=STAGED_DEPTH, agent_society=True, operational=True)):
        prompt = "这句话故意不含旧规则里的动作词，但模型语义判断为真实任务。"
        assert should_apply_agent_society_protocol(prompt)
        assert should_apply_operational_execution_protocol(prompt)
        assert classify_interaction_kind(prompt) == TASK_KIND
        assert classify_execution_depth(prompt) == STAGED_DEPTH


def test_model_frame_can_keep_keyword_heavy_text_as_chat() -> None:
    with entry_frame(frame(kind=CHAT_KIND, depth=ATOMIC_DEPTH, agent_society=False, operational=False)):
        prompt = "登录、部署、修复、新闻、天气这些词只是我在讨论规则，不是在让你执行。"
        assert not should_apply_agent_society_protocol(prompt)
        assert not should_apply_operational_execution_protocol(prompt)
        assert classify_interaction_kind(prompt) == CHAT_KIND
        assert classify_execution_depth(prompt) == ATOMIC_DEPTH


def test_model_unavailable_does_not_force_task_protocol() -> None:
    result = classify_entry_policy(
        "这是一句复杂但模型不可用时不应被关键词强行判成任务的话。",
        model_caller=lambda _messages: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    assert result.interaction_kind == CHAT_KIND
    assert result.execution_depth == ATOMIC_DEPTH
    assert not result.apply_agent_society


def test_agentic_depth_and_self_improvement_are_model_decisions() -> None:
    with entry_frame(frame(kind=TASK_KIND, depth=AGENTIC_DEPTH, agent_society=True, operational=True, self_improvement=True)):
        prompt = "请沿正确方向补齐自身能力，验证后再回到原任务。"
        assert should_apply_agent_society_protocol(prompt)
        assert should_apply_self_improvement_protocol(prompt)
        assert classify_execution_depth(prompt) == AGENTIC_DEPTH
        protocol = build_multistep_task_protocol(prompt)
        assert "execution_depth: agentic" in protocol
        assert "LLM semantic contract layer, not keyword/regex routing" in protocol


def test_staged_protocol_contains_keyword_regex_boundary() -> None:
    protocol = build_multistep_task_protocol("任何文本", execution_depth=STAGED_DEPTH)

    assert "execution_depth: staged" in protocol
    assert "Keywords or regex may only be used after a tool is selected" in protocol


def main() -> int:
    test_entry_policy_prompt_states_semantic_routing_law()
    test_simple_chat_branch_is_the_only_non_model_shortcut()
    test_model_frame_controls_task_classification_not_keywords()
    test_model_frame_can_keep_keyword_heavy_text_as_chat()
    test_model_unavailable_does_not_force_task_protocol()
    test_agentic_depth_and_self_improvement_are_model_decisions()
    test_staged_protocol_contains_keyword_regex_boundary()
    print("agent_society_entry_policy_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
