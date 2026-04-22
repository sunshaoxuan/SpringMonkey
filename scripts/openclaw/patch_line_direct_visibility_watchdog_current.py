#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import shutil


def resolve_monitor_bundle(dist: Path) -> Path:
    candidates = [p for p in dist.glob("monitor-*.js") if p.is_file()]
    if not candidates:
        raise SystemExit("line monitor bundle not found")
    scored: list[tuple[int, float, Path]] = []
    for candidate in candidates:
        text = candidate.read_text(encoding="utf-8", errors="ignore")
        score = 0
        if "received message from " in text:
            score += 3
        if "no response generated" in text:
            score += 3
        if "showLoadingAnimation" in text:
            score += 2
        scored.append((score, candidate.stat().st_mtime, candidate))
    scored.sort(reverse=True)
    if not scored or scored[0][0] <= 0:
        raise SystemExit("line monitor bundle with direct reply flow not found")
    return scored[0][2]


def main() -> int:
    dist = Path("/usr/lib/node_modules/openclaw/dist")
    target = resolve_monitor_bundle(dist)
    text = target.read_text(encoding="utf-8")

    if "let directVisibleWatchdog = null;" not in text:
        ack_phrase = "received message from "
        ack_idx = text.find(ack_phrase)
        if ack_idx < 0:
            raise SystemExit("line direct visibility ack anchor not found")
        line_end = text.find("\n", ack_idx)
        if line_end < 0:
            raise SystemExit("line direct visibility ack line terminator not found")
        text = text[: line_end + 1] + "\t\t\tlet directVisibleWatchdog = null;\n" + text[line_end + 1 :]

    if '"收到，我已经开始处理这项任务；如果耗时较长，我会继续汇报进度。"' not in text:
        text, count = re.subn(
            r'const textLimit = 5e3;\s*let replyTokenUsed = false;',
            'const textLimit = 5e3;\n\t\t\t\tlet replyTokenUsed = false;\n\t\t\t\tif (ctx.userId && !ctx.isGroup) {\n\t\t\t\t\tawait pushMessageLine(ctxPayload.From, "收到，我已经开始处理这项任务；如果耗时较长，我会继续汇报进度。", { accountId: ctx.accountId }).catch((ackErr) => {\n\t\t\t\t\t\tlogVerbose(`line: initial direct-task ack failed (non-fatal): ${String(ackErr)}`);\n\t\t\t\t\t});\n\t\t\t\t\tdirectVisibleWatchdog = setTimeout(() => {\n\t\t\t\t\t\tpushMessageLine(ctxPayload.From, "任务仍在处理中。我已经进入执行阶段；如果当前步骤卡住，稍后会继续汇报阻塞点或结果。", { accountId: ctx.accountId }).catch((watchdogErr) => {\n\t\t\t\t\t\t\tlogVerbose(`line: direct-task watchdog update failed (non-fatal): ${String(watchdogErr)}`);\n\t\t\t\t\t\t});\n\t\t\t\t\t}, 45e3);\n\t\t\t\t}',
            text,
            count=1,
        )
        if count != 1:
            raise SystemExit("line direct visibility try anchor not found")

    deliver_anchor = '''recordChannelRuntimeState({\n\t\t\t\t\t\t\t\tchannel: "line",\n\t\t\t\t\t\t\t\taccountId: resolvedAccountId,\n\t\t\t\t\t\t\t\tstate: { lastOutboundAt: Date.now() }\n\t\t\t\t\t\t\t});\n'''
    deliver_replacement = '''recordChannelRuntimeState({\n\t\t\t\t\t\t\t\tchannel: "line",\n\t\t\t\t\t\t\t\taccountId: resolvedAccountId,\n\t\t\t\t\t\t\t\tstate: { lastOutboundAt: Date.now() }\n\t\t\t\t\t\t\t});\n\t\t\t\t\t\t\tif (directVisibleWatchdog) {\n\t\t\t\t\t\t\t\tclearTimeout(directVisibleWatchdog);\n\t\t\t\t\t\t\t\tdirectVisibleWatchdog = null;\n\t\t\t\t\t\t\t}\n'''
    if "if (directVisibleWatchdog)" not in text:
        if deliver_anchor not in text:
            raise SystemExit("line direct visibility deliver anchor not found")
        text = text.replace(deliver_anchor, deliver_replacement, 1)

    no_response_anchor = '''if (!queuedFinal) logVerbose(`line: no response generated for message from ${ctxPayload.From}`);\n'''
    no_response_replacement = '''if (!queuedFinal) {\n\t\t\t\t\tif (directVisibleWatchdog) {\n\t\t\t\t\t\tclearTimeout(directVisibleWatchdog);\n\t\t\t\t\t\tdirectVisibleWatchdog = null;\n\t\t\t\t\t}\n\t\t\t\t\tif (ctx.userId && !ctx.isGroup) await pushMessageLine(ctxPayload.From, "这轮处理没有正常产出结果文本。我已记录为执行异常，接下来需要检查阻塞点。", { accountId: ctx.accountId }).catch((fallbackErr) => {\n\t\t\t\t\t\tlogVerbose(`line: no-response fallback push failed (non-fatal): ${String(fallbackErr)}`);\n\t\t\t\t\t});\n\t\t\t\t\tlogVerbose(`line: no response generated for message from ${ctxPayload.From}`);\n\t\t\t\t}\n'''
    if '"这轮处理没有正常产出结果文本。我已记录为执行异常，接下来需要检查阻塞点。"' not in text:
        if no_response_anchor not in text:
            raise SystemExit("line direct visibility no-response anchor not found")
        text = text.replace(no_response_anchor, no_response_replacement, 1)

    finally_anchor = '''} finally {\n\t\t\t\tstopLoading?.();\n\t\t\t}\n'''
    finally_replacement = '''} finally {\n\t\t\t\tif (directVisibleWatchdog) {\n\t\t\t\t\tclearTimeout(directVisibleWatchdog);\n\t\t\t\t\tdirectVisibleWatchdog = null;\n\t\t\t\t}\n\t\t\t\tstopLoading?.();\n\t\t\t}\n'''
    if 'clearTimeout(directVisibleWatchdog);' not in text:
        if finally_anchor not in text:
            raise SystemExit("line direct visibility finally anchor not found")
        text = text.replace(finally_anchor, finally_replacement, 1)

    backup = target.with_name(f"{target.name}.bak-line-direct-visibility-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(target, backup)
    target.write_text(text, encoding="utf-8")
    print(f"PATCHED_BUNDLE {target}")
    print(f"BACKUP_BUNDLE {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
