#!/usr/bin/env python3
"""
Patch current OpenClaw pi-embedded bundle so manual Discord news reruns
must trigger the formal cron job instead of freeform generation.

Behavior:
- Detect manual news rerun prompts from the current Discord turn.
- Queue `openclaw cron run <jobId>` asynchronously.
- Disable tools for the main chat turn.
- Force the main turn to reply with one exact confirmation/failure sentence.

This script targets the current bundle shape that still contains
`async function runEmbeddedAttempt(params) {` and the prompt-build path with
`let effectivePrompt = prependBootstrapPromptWarning(...)`.
"""
from __future__ import annotations

from pathlib import Path
import shutil


DIST_DIR = Path("/usr/lib/node_modules/openclaw/dist")


HELPERS_BLOCK = """function normalizeManualNewsChannel(value) {
\treturn String(value ?? "").trim().toLowerCase();
}
function sanitizeManualNewsPromptCurrent(text) {
\tlet value = String(text || "");
\tvalue = value.replace(/<relevant-memories>[\\s\\S]*?<\\/relevant-memories>/giu, " ");
\tvalue = value.replace(/```json[\\s\\S]*?```/giu, " ");
\tvalue = value.replace(/Conversation info \\(untrusted metadata\\):/giu, " ");
\tvalue = value.replace(/按系统要求原样回复。?/giu, " ");
\treturn value.replace(/\\s+/g, " ").trim();
}
function isManualNewsRerunPromptCurrent(text) {
\treturn /(重跑|重新跑|重新执行|手动重跑|立即手动重跑|立即重跑|再次执行|再跑一次|再跑一遍|跑一次|跑一遍|来一次|立即执行|马上执行|现在就跑|触发|rerun|run again|restart)/iu.test(String(text || ""));
}
function hasExplicitNewsSlotHintCurrent(text) {
\treturn /(17\\s*[:：点时]|17点|17時|十七点|1700)/u.test(String(text || "")) || /(0?9\\s*[:：点时]|9点|09点|09時|9時|0900)/u.test(String(text || "")) || /news-digest-jst-(0900|1700)/iu.test(String(text || ""));
}
function shouldForceFormalNewsManualRun(params, promptText) {
\tconst channel = normalizeManualNewsChannel(params?.messageChannel ?? params?.messageProvider);
\tif (channel !== "discord") return false;
\tconst text = sanitizeManualNewsPromptCurrent(promptText);
\tif (!isManualNewsRerunPromptCurrent(text) || !hasExplicitNewsSlotHintCurrent(text)) return false;
\treturn /(新闻|播报|digest|news|摘要|cron|正式任务|正式规则)/iu.test(text);
}
function selectFormalNewsJobNameCurrent(promptText) {
\tconst text = sanitizeManualNewsPromptCurrent(promptText);
\tif (/(17\\s*[:：点时]|17点|17時|十七点|1700)/u.test(text)) return "news-digest-jst-1700";
\tif (/(0?9\\s*[:：点时]|9点|09点|09時|9時|0900)/u.test(text)) return "news-digest-jst-0900";
\treturn "news-digest-jst-1700";
}
async function loadFormalNewsJobCurrent(jobName) {
\tconst jobsPath = "/var/lib/openclaw/.openclaw/cron/jobs.json";
\tconst raw = await fs$1.readFile(jobsPath, "utf8");
\tconst jobsDoc = JSON.parse(raw);
\tconst job = Array.isArray(jobsDoc?.jobs) ? jobsDoc.jobs.find((item) => item?.name === jobName) : null;
\tif (!job) throw new Error(`formal news job missing: ${jobName}`);
\tconst jobId = String(job.id || "").trim();
\tif (!jobId) throw new Error(`formal news job id missing: ${jobName}`);
\treturn { jobName, jobId };
}
async function queueFormalNewsJobRunCurrent(promptText) {
\tconst jobName = selectFormalNewsJobNameCurrent(promptText);
\tconst { jobId } = await loadFormalNewsJobCurrent(jobName);
\tconst env = { ...process.env, HOME: "/var/lib/openclaw" };
\tconst timeoutMs = 120000;
\tconst command = typeof process.getuid === "function" && process.getuid() === 0 ? "runuser" : "openclaw";
\tconst args = typeof process.getuid === "function" && process.getuid() === 0 ? ["-u", "openclaw", "--", "env", "HOME=/var/lib/openclaw", "openclaw", "cron", "run", jobId] : ["cron", "run", jobId];
\tconst execResult = await new Promise((resolve, reject) => {
\t\tconst child = spawn(command, args, { env });
\t\tlet stdout = "";
\t\tlet stderr = "";
\t\tconst tid = setTimeout(() => {
\t\t\ttry {
\t\t\t\tchild.kill("SIGKILL");
\t\t\t} catch {}
\t\t\treject(new Error(`cron run timed out after ${timeoutMs}ms`));
\t\t}, timeoutMs);
\t\tchild.stdout?.on("data", (chunk) => {
\t\t\tstdout += chunk.toString();
\t\t});
\t\tchild.stderr?.on("data", (chunk) => {
\t\t\tstderr += chunk.toString();
\t\t});
\t\tchild.on("error", (err) => {
\t\t\tclearTimeout(tid);
\t\t\treject(err);
\t\t});
\t\tchild.on("close", (code) => {
\t\t\tclearTimeout(tid);
\t\t\tresolve({ status: code, stdout, stderr });
\t\t});
\t});
\tif (execResult.status !== 0) throw new Error(`cron run failed (${execResult.status}): ${(execResult.stderr || execResult.stdout || "").trim()}`);
\tlet runId = "";
\tconst raw = String(execResult.stdout || "").trim();
\ttry {
\t\tconst parsed = JSON.parse(raw);
\t\tif (parsed && typeof parsed.runId === "string") runId = parsed.runId;
\t} catch {}
\treturn { jobName, jobId, runId };
}
function buildForcedExactReplySystemPromptCurrent(replyText) {
\treturn [
\t\t"[MANDATORY SYSTEM OVERRIDE — DO NOT IGNORE]",
\t\t"",
\t\t"A formal news cron job has already been handled outside this chat turn.",
\t\t"Do NOT generate any news content, summary, digest, explanation, search results, or process notes.",
\t\t"Do NOT call any tools.",
\t\t`Respond with EXACTLY this one sentence in Chinese: 「${replyText}」`
\t].join("\\n");
}"""


OLD_RUN_START = """async function runEmbeddedAttempt(params) {
\tconst resolvedWorkspace = resolveUserPath(params.workspaceDir);
\tconst runAbortController = new AbortController();
\tensureGlobalUndiciEnvProxyDispatcher();
\tensureGlobalUndiciStreamTimeouts();
\tlog$16.debug(`embedded run start: runId=${params.runId} sessionId=${params.sessionId} provider=${params.provider} model=${params.modelId} thinking=${params.thinkLevel} messageChannel=${params.messageChannel ?? params.messageProvider ?? "unknown"}`);
\tawait fs$1.mkdir(resolvedWorkspace, { recursive: true });"""

NEW_RUN_START = """async function runEmbeddedAttempt(params) {
\tconst resolvedWorkspace = resolveUserPath(params.workspaceDir);
\tconst runAbortController = new AbortController();
\tensureGlobalUndiciEnvProxyDispatcher();
\tensureGlobalUndiciStreamTimeouts();
\tlog$16.debug(`embedded run start: runId=${params.runId} sessionId=${params.sessionId} provider=${params.provider} model=${params.modelId} thinking=${params.thinkLevel} messageChannel=${params.messageChannel ?? params.messageProvider ?? "unknown"}`);
\tconst manualNewsPromptText = typeof params.prompt === "string" ? params.prompt : "";
\tlet forcedManualNewsReply = null;
\tif (shouldForceFormalNewsManualRun(params, manualNewsPromptText)) {
\t\tparams.disableTools = true;
\t\ttry {
\t\t\tconst queued = await queueFormalNewsJobRunCurrent(manualNewsPromptText);
\t\t\tforcedManualNewsReply = `已触发正式新闻任务 ${queued.jobName}${queued.runId ? `（runId: ${queued.runId}）` : ""}，结果将由正式任务单独投递。`;
\t\t\tlog$16.info(`[intent-router-current] manual news rerun queued job=${queued.jobName}${queued.runId ? ` runId=${queued.runId}` : ""} tools-disabled=1`);
\t\t} catch (error) {
\t\t\tconst reason = String(error?.message ?? error ?? "unknown error").replace(/\\s+/g, " ").trim().slice(0, 160);
\t\t\tforcedManualNewsReply = `正式新闻任务触发失败：${reason}`;
\t\t\tlog$16.warn(`[intent-router-current] manual news rerun queue failed: ${reason}`);
\t\t}
\t}
\tawait fs$1.mkdir(resolvedWorkspace, { recursive: true });"""


OLD_PROMPT_START = """\t\t\ttry {
\t\t\t\tconst promptStartedAt = Date.now();
\t\t\t\tlet effectivePrompt = prependBootstrapPromptWarning(params.prompt, bootstrapPromptWarning.lines, { preserveExactPrompt: heartbeatPrompt });
\t\t\t\tconst hookCtx = {"""

NEW_PROMPT_START = """\t\t\ttry {
\t\t\t\tconst promptStartedAt = Date.now();
\t\t\t\tlet effectivePrompt = prependBootstrapPromptWarning(params.prompt, bootstrapPromptWarning.lines, { preserveExactPrompt: heartbeatPrompt });
\t\t\t\tif (forcedManualNewsReply) {
\t\t\t\t\tconst forcedSystemPrompt = buildForcedExactReplySystemPromptCurrent(forcedManualNewsReply);
\t\t\t\t\tapplySystemPromptOverrideToSession(activeSession, forcedSystemPrompt);
\t\t\t\t\tsystemPromptText = forcedSystemPrompt;
\t\t\t\t\teffectivePrompt = "按系统要求原样回复。";
\t\t\t\t}
\t\t\t\tconst hookCtx = {"""


def detect_target() -> Path:
    candidates = sorted(DIST_DIR.glob("pi-embedded-*.js"))
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "async function runEmbeddedAttempt(params) {" in text and "let effectivePrompt = prependBootstrapPromptWarning(params.prompt" in text:
            return path
    raise SystemExit("current pi-embedded target not found")


def main() -> None:
    target = detect_target()
    backup = target.with_name(f"{target.name}.bak-manual-news-current")
    text = target.read_text(encoding="utf-8")
    if "sanitizeManualNewsPromptCurrent" in text and "buildForcedExactReplySystemPromptCurrent" in text:
        print(f"PATCH_CURRENT_MANUAL_NEWS_ALREADY_OK {target}")
        return
    if not backup.exists():
        shutil.copy2(target, backup)
    old_helpers_start = """function normalizeManualNewsChannel(value) {
\treturn String(value ?? "").trim().toLowerCase();
}
function isManualNewsRerunPromptCurrent(text) {
\treturn /(重跑|重新跑|重新执行|手动重跑|立即手动重跑|立即重跑|再次执行|再跑一次|再跑一遍|跑一次|跑一遍|来一次|立即执行|马上执行|现在就跑|触发|rerun|run again|restart)/iu.test(String(text || ""));
}
function hasExplicitNewsSlotHintCurrent(text) {
\treturn /(17\\s*[:：点时]|17点|17時|十七点|1700)/u.test(String(text || "")) || /(0?9\\s*[:：点时]|9点|09点|09時|9時|0900)/u.test(String(text || "")) || /news-digest-jst-(0900|1700)/iu.test(String(text || ""));
}
function shouldForceFormalNewsManualRun(params, promptText) {
\tconst channel = normalizeManualNewsChannel(params?.messageChannel ?? params?.messageProvider);
\tif (channel !== "discord") return false;
\tconst text = String(promptText || "");
\tif (!isManualNewsRerunPromptCurrent(text) || !hasExplicitNewsSlotHintCurrent(text)) return false;
\treturn /(新闻|播报|digest|news|摘要|cron|正式任务|正式规则)/iu.test(text);
}
function selectFormalNewsJobNameCurrent(promptText) {
\tconst text = String(promptText || "");
\tif (/(17\\s*[:：点时]|17点|17時|十七点|1700)/u.test(text)) return "news-digest-jst-1700";
\tif (/(0?9\\s*[:：点时]|9点|09点|09時|9時|0900)/u.test(text)) return "news-digest-jst-0900";
\treturn "news-digest-jst-1700";
}"""
    anchor = "async function runEmbeddedAttempt(params) {"
    if old_helpers_start in text:
        text = text.replace(old_helpers_start, HELPERS_BLOCK.rstrip(), 1)
    elif HELPERS_BLOCK not in text:
        idx = text.find(anchor)
        if idx < 0:
            raise SystemExit("runEmbeddedAttempt anchor not found")
        text = text[:idx] + HELPERS_BLOCK + "\n" + text[idx:]
    if OLD_RUN_START not in text:
        raise SystemExit("run start block not found")
    text = text.replace(OLD_RUN_START, NEW_RUN_START, 1)
    if OLD_PROMPT_START not in text:
        raise SystemExit("prompt override block not found")
    text = text.replace(OLD_PROMPT_START, NEW_PROMPT_START, 1)
    target.write_text(text, encoding="utf-8")
    print(f"PATCH_CURRENT_MANUAL_NEWS_OK {target}")


if __name__ == "__main__":
    main()
