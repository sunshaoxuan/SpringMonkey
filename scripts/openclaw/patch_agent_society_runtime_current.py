#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil


def main() -> int:
    dist = Path("/usr/lib/node_modules/openclaw/dist")
    target = dist / "agent-runner.runtime-CTlghBhJ.js"
    if not target.exists():
        raise SystemExit("agent-runner runtime bundle not found")

    text = target.read_text(encoding="utf-8")

    old_block = '''\tconst shouldApplyOperationalExecutionProtocol = (() => {\n\t\tif (isHeartbeat || sessionCtx.ChatType !== "direct") return false;\n\t\tconst promptText = typeof followupRun.prompt === "string" ? followupRun.prompt : "";\n\t\tif (!promptText.trim()) return false;\n\t\tconst hasOperationVerb = /登录|登入|log\\s?in|sign\\s?in|change\\s+password|reset\\s+password|修改密码|重置密码|打开|访问|进入|navigate|open|visit|click|点击|search|查找|设置|配置|保存密码|提交|上传|download|upload|修复|排查|测试/u.test(promptText);\n\t\tconst hasOperationTarget = /邮箱|email|mail|账号|account|网站|网页|browser|登录页|设置页|password|密码|google|docs|小红书|line|discord|slack|notion|service|系统|portal|dashboard/u.test(promptText);\n\t\treturn hasOperationVerb && hasOperationTarget;\n\t})();\n\tconst OPERATIONAL_EXECUTION_PROTOCOL = `[runtime-operational-execution-protocol]\\nThis is an operational task. Do not rely on one long thinking pass and do not stop at analysis.\\nUse a plan-execute-observe-replan loop:\\n1. identify the concrete goal and likely target system\\n2. break the task into ordered executable steps\\n3. choose the right tool for the current step\\n4. execute exactly one step\\n5. inspect the result before deciding the next step\\n6. continue until completed or a concrete blocker is proven\\nTool selection rules:\\n- For website or account tasks, prefer browser-first execution.\\n- If the login URL or system is unknown, use browser or web discovery first to identify it.\\n- Use exec/read only for local files, host config, or command-line verification.\\n- Do not claim a password was changed, saved, or verified unless the observed result proves it.\\n- If credentials, 2FA, captcha, permissions, or confirmation are missing, report the exact blocker instead of pretending completion.\\nFinal response rules:\\n- Report what you actually did.\\n- Report the current state.\\n- Report any remaining blocker or next step if unfinished.`;\n\tif (shouldApplyOperationalExecutionProtocol && typeof followupRun.prompt === "string" && !followupRun.prompt.includes("[runtime-operational-execution-protocol]")) followupRun.prompt = `${OPERATIONAL_EXECUTION_PROTOCOL}\\n\\nUser task:\\n${followupRun.prompt}`;\n\tconst shouldEmitToolResult = createShouldEmitToolResult({\n\t\tsessionKey,\n\t\tstorePath,\n\t\tresolvedVerboseLevel\n\t});\n'''
    new_block = '''\tconst shouldApplyOperationalExecutionProtocol = (() => {\n\t\tif (isHeartbeat || sessionCtx.ChatType !== "direct") return false;\n\t\tconst promptText = typeof followupRun.prompt === "string" ? followupRun.prompt : "";\n\t\tif (!promptText.trim()) return false;\n\t\tconst hasOperationVerb = /登录|登入|log\\s?in|sign\\s?in|change\\s+password|reset\\s+password|修改密码|重置密码|打开|访问|进入|navigate|open|visit|click|点击|search|查找|设置|配置|保存密码|提交|上传|download|upload|修复|排查|测试/u.test(promptText);\n\t\tconst hasOperationTarget = /邮箱|email|mail|账号|account|网站|网页|browser|登录页|设置页|password|密码|google|docs|小红书|line|discord|slack|notion|service|系统|portal|dashboard/u.test(promptText);\n\t\treturn hasOperationVerb && hasOperationTarget;\n\t})();\n\tconst shouldApplyAgentSocietyProtocol = (() => {\n\t\tif (isHeartbeat || sessionCtx.ChatType !== "direct") return false;\n\t\tconst promptText = typeof followupRun.prompt === "string" ? followupRun.prompt : "";\n\t\tif (!promptText.trim()) return false;\n\t\tconst hasTaskingSignal = /并|然后|再|同时|顺便|继续|并且|此外|还要|以及|总结|汇报|报告|验证|记录|记住|remember|report|verify|save|continue|follow\\s?up|status/u.test(promptText);\n\t\tconst hasExecutionSignal = /帮我|请你|需要|去|处理|执行|完成|安排|登录|修改|检查|查找|修复|配置|设置|创建|生成|登录邮箱|改密码|保存密码/u.test(promptText);\n\t\treturn shouldApplyOperationalExecutionProtocol || hasTaskingSignal && hasExecutionSignal;\n\t})();\n\tconst OPERATIONAL_EXECUTION_PROTOCOL = `[runtime-operational-execution-protocol]\\nThis is an operational task. Do not rely on one long thinking pass and do not stop at analysis.\\nUse a plan-execute-observe-replan loop:\\n1. identify the concrete goal and likely target system\\n2. break the task into ordered executable steps\\n3. choose the right tool for the current step\\n4. execute exactly one step\\n5. inspect the result before deciding the next step\\n6. continue until completed or a concrete blocker is proven\\nTool selection rules:\\n- For website or account tasks, prefer browser-first execution.\\n- If the login URL or system is unknown, use browser or web discovery first to identify it.\\n- Use exec/read only for local files, host config, or command-line verification.\\n- Do not claim a password was changed, saved, or verified unless the observed result proves it.\\n- If credentials, 2FA, captcha, permissions, or confirmation are missing, report the exact blocker instead of pretending completion.\\nFinal response rules:\\n- Report what you actually did.\\n- Report the current state.\\n- Report any remaining blocker or next step if unfinished.`;\n\tconst GOAL_INTENT_TASK_AGENT_SOCIETY_PROTOCOL = `[runtime-goal-intent-task-agent-society-protocol]\\nTreat this as a controlled agent-society task, not a single-pass reply.\\nExecution model:\\n1. derive one primary goal and any bounded secondary goals\\n2. extract all relevant intents from the user request, including operational, verification, memory, reporting, and continuation intents\\n3. convert intents into tasks with priorities and success conditions\\n4. convert only the current active task into concrete executable steps\\n5. for each step, choose the best tool path, execute one step, inspect the observation, and then decide the next step\\n6. allow new sub-intents or helper tasks only when they are justified by observation\\n7. force every child intent or task to converge back to the parent goal\\nConvergence rules:\\n- Never let a child task drift away from the primary goal.\\n- If a new subproblem does not clearly serve the goal, defer or discard it.\\n- Prefer finite progress over uncontrolled branching.\\nTask decomposition rules:\\n- Support multiple intents in one message.\\n- Support multiple tasks per intent when needed.\\n- Support verification and reporting as first-class tasks instead of afterthoughts.\\nStep execution rules:\\n- Each step must have one immediate objective, one expected observation, and one success check.\\n- Do not jump to final claims before observed evidence exists.\\n- If a step fails, classify the blocker and replan instead of repeating blind attempts.\\nTool ecology rules:\\n- Prefer proven existing tools first.\\n- If a reusable capability gap appears, create or refine a helper tool, script, parser, or procedure instead of repeating the same failed tactic.\\n- Treat good helper tools as reusable capability, not one-off hacks.\\nRole rules:\\n- Act internally as governor, decomposer, worker, verifier, and reporter even if one model instance performs multiple roles.\\n- Governor protects the primary goal and boundaries.\\n- Decomposer extracts intents and tasks.\\n- Worker executes the current step.\\n- Verifier checks real end state and evidence.\\n- Reporter keeps the user informed about status and result.\\nReporting rules:\\n- Make it clear which goal is being advanced now.\\n- If work expands, say why that expansion is necessary.\\n- Final output must include achieved end state, evidence, remaining blocker, or next action.`;\n\tif (shouldApplyAgentSocietyProtocol && typeof followupRun.prompt === "string" && !followupRun.prompt.includes("[runtime-goal-intent-task-agent-society-protocol]")) {\n\t\tconst protocolParts = [];\n\t\tif (!followupRun.prompt.includes("[runtime-operational-execution-protocol]")) protocolParts.push(OPERATIONAL_EXECUTION_PROTOCOL);\n\t\tprotocolParts.push(GOAL_INTENT_TASK_AGENT_SOCIETY_PROTOCOL);\n\t\tfollowupRun.prompt = `${protocolParts.join("\\n\\n")}\\n\\nUser task:\\n${followupRun.prompt}`;\n\t}\n\tconst shouldEmitToolResult = createShouldEmitToolResult({\n\t\tsessionKey,\n\t\tstorePath,\n\t\tresolvedVerboseLevel\n\t});\n'''

    if "[runtime-goal-intent-task-agent-society-protocol]" not in text:
        if old_block in text:
            text = text.replace(old_block, new_block, 1)
        else:
            fallback_anchor = '''\tconst shouldEmitToolResult = createShouldEmitToolResult({\n\t\tsessionKey,\n\t\tstorePath,\n\t\tresolvedVerboseLevel\n\t});\n'''
            if fallback_anchor not in text:
                raise SystemExit("agent society protocol anchor not found")
            text = text.replace(fallback_anchor, new_block, 1)

    workspace = Path("/var/lib/openclaw/.openclaw/workspace")
    workspace.mkdir(parents=True, exist_ok=True)
    policy_file = workspace / "AGENT_SOCIETY_RUNTIME.md"
    policy_text = '''# Agent Society Runtime Bridge

This host uses a transitional runtime guard for direct task execution.

Core expectations:

- extract primary and secondary goals
- extract multiple intents when they exist
- derive tasks and only then derive executable steps
- select tools per step instead of relying on one long thinking pass
- allow bounded sub-intent expansion only when observation justifies it
- converge all child work back to the parent goal
- create or refine reusable helper tools when the same capability gap recurs
- verify end state with observed evidence before claiming completion
- keep the user informed with visible acceptance, progress, and completion or blocker status
'''
    policy_file.write_text(policy_text, encoding="utf-8")

    backup = target.with_name(f"{target.name}.bak-agent-society-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(target, backup)
    target.write_text(text, encoding="utf-8")
    print(f"PATCHED_BUNDLE {target}")
    print(f"BACKUP_BUNDLE {backup}")
    print(f"WORKSPACE_POLICY {policy_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
