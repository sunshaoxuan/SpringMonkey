#!/usr/bin/env python3
"""
Patch current pi-embedded intent router state to stable manual-news rerun routing.

Target state:
- Discord chat stays on local qwen.
- Manual news rerun commands bypass classifier heuristics when appropriate.
- Manual rerun queues formal `openclaw cron run <jobId>` asynchronously.
- Primary routing failures degrade to codex instead of returning null.

This script is for the host's *current* router shape where:
- `buildFormalNewsManualPrompt` exists
- `queueFormalNewsJobRun` does not exist
- `maybeRouteDiscordIntent` only reroutes `news_task` to a formal prompt
"""

from pathlib import Path
import shutil


TARGET = Path("/usr/lib/node_modules/openclaw/dist/pi-embedded-BYdcxQ5A.js")
BACKUP = Path(
    "/usr/lib/node_modules/openclaw/dist/pi-embedded-BYdcxQ5A.js.bak-20260405-current-to-v7"
)


START_MARKER = 'async function classifyDiscordIntent(promptText) {'
END_MARKER = '// INTENT ROUTER END'


NEW_BLOCK = """async function classifyDiscordIntent(promptText) {
\tconst ac = new AbortController();
\tconst tid = setTimeout(() => ac.abort(), 12000);
\tlet response;
\ttry {
\t\tresponse = await fetch("http://ccnode.briconbric.com:22545/api/generate", {
\t\t\tmethod: "POST",
\t\t\theaders: { "content-type": "application/json" },
\t\t\tsignal: ac.signal,
\t\t\tbody: JSON.stringify({
\t\t\t\tmodel: "qwen3:14b",
\t\t\t\tprompt: [
\t\t\t\t\t"Classify the user's intent into exactly one label.",
\t\t\t\t\t"Allowed labels: chat, task_control, news_task, repo_sync.",
\t\t\t\t\t"Definitions:",
\t\t\t\t\t"- chat: normal conversation, questions, explanations, introductions, brainstorming.",
\t\t\t\t\t"- task_control: change settings, apply/verify/restart/reload/execute/inspect tasks or services, memory ingestion, version checks, maintenance.",
\t\t\t\t\t"- news_task: rerun/generate/publish/test a news broadcast or news digest.",
\t\t\t\t\t"- repo_sync: write, commit, push, sync docs/config/work products to git/repo.",
\t\t\t\t\t"Return JSON only in the form {\\\"intent\\\":\\\"<label>\\\"}.",
\t\t\t\t\t"User message:",
\t\t\t\t\tpromptText,
\t\t\t\t\t"JSON:"
\t\t\t\t].join("\\n"),
\t\t\t\tstream: false,
\t\t\t\tkeep_alive: "8h",
\t\t\t\toptions: { temperature: 0 }
\t\t\t})
\t\t});
\t} finally {
\t\tclearTimeout(tid);
\t}
\tif (!response || !response.ok) throw new Error(`intent classifier http ${response?.status ?? "no_response"}`);
\tconst data = await response.json();
\tconst raw = String(data?.response ?? "").trim();
\tconst jsonStart = raw.indexOf("{");
\tconst jsonEnd = raw.lastIndexOf("}");
\tconst parsed = JSON.parse(jsonStart >= 0 && jsonEnd > jsonStart ? raw.slice(jsonStart, jsonEnd + 1) : raw);
\tconst intent = typeof parsed?.intent === "string" ? parsed.intent.trim() : "";
\tif (intent === "chat" || intent === "task_control" || intent === "news_task" || intent === "repo_sync") return intent;
\tthrow new Error(`invalid intent classifier label: ${raw}`);
}
function selectFormalNewsJobName(promptText) {
\tconst text = String(promptText || "");
\tif (/17\\s*[:：点时]/u.test(text) || /17点/u.test(text) || /17時/u.test(text)) return "news-digest-jst-1700";
\tif (/9\\s*[:：点时]/u.test(text) || /09\\s*[:：点时]/u.test(text) || /09点/u.test(text) || /9点/u.test(text) || /09時/u.test(text) || /9時/u.test(text)) return "news-digest-jst-0900";
\treturn "news-digest-jst-1700";
}
function hasExplicitNewsSlotHint(promptText) {
\tconst text = String(promptText || "");
\treturn /(17\\s*[:：点时]|17点|17時|十七点|1700)/u.test(text)
\t\t|| /(0?9\\s*[:：点时]|9点|09点|09時|9時|0900)/u.test(text)
\t\t|| /news-digest-jst-(0900|1700)/iu.test(text);
}
function isManualNewsRerunPrompt(promptText) {
\tconst text = String(promptText || "");
\treturn /(重跑|重新跑|重新执行|手动重跑|立即手动重跑|立即重跑|再次执行|再跑一次|再跑一遍|跑一次|跑一遍|来一次|立即执行|马上执行|现在就跑|触发|rerun|run again|restart)/iu.test(text);
}
function shouldOverrideToNewsTask(promptText) {
\tconst text = String(promptText || "");
\tif (!isManualNewsRerunPrompt(text) || !hasExplicitNewsSlotHint(text)) return false;
\treturn /(新闻|播报|digest|news|摘要|cron|正式任务|正式规则)/iu.test(text);
}
async function loadFormalNewsJob(jobName) {
\tconst jobsPath = "/var/lib/openclaw/.openclaw/cron/jobs.json";
\tconst raw = await fs.readFile(jobsPath, "utf8");
\tconst jobsDoc = JSON.parse(raw);
\tconst job = Array.isArray(jobsDoc?.jobs) ? jobsDoc.jobs.find((item) => item?.name === jobName) : null;
\tif (!job) throw new Error(`formal news job missing: ${jobName}`);
\tconst formalMessage = String(job?.payload?.message || "").trim();
\tif (!formalMessage) throw new Error(`formal news job payload missing: ${jobName}`);
\treturn { jobName, jobId: String(job.id || ""), formalMessage };
}
async function buildFormalNewsManualPrompt(promptText) {
\tconst jobName = selectFormalNewsJobName(promptText);
\tconst { formalMessage } = await loadFormalNewsJob(jobName);
\treturn [
\t\t"你当前不是在普通聊天，而是在执行一次正式新闻任务的手动重跑。",
\t\t`必须严格按正式任务 ${jobName} 的既有 payload 执行，不得临时改写任务目标，不得用占位结果敷衍。`,
\t\t"只允许输出最终播报成稿；不要输出过程说明、计划、状态播报、占位标题或伪完成信息。",
\t\t"如果抓取失败，必须在正式规则允许的来源和回退链内继续完成；如果最终仍不能满足规则，就明确报告失败点，但不得伪造合格播报。",
\t\t"以下是该正式任务的权威定义，必须原样遵守：",
\t\tformalMessage
\t].join("\\n\\n");
}
async function queueFormalNewsJobRun(promptText) {
\tconst jobName = selectFormalNewsJobName(promptText);
\tconst { jobId } = await loadFormalNewsJob(jobName);
\tconst env = { ...process.env, HOME: "/var/lib/openclaw" };
\tconst timeoutMs = 120000;
\tconst command = typeof process.getuid === "function" && process.getuid() === 0 ? "runuser" : "openclaw";
\tconst args = typeof process.getuid === "function" && process.getuid() === 0
\t\t? ["-u", "openclaw", "--", "env", "HOME=/var/lib/openclaw", "openclaw", "cron", "run", jobId]
\t\t: ["cron", "run", jobId];
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
\tif (execResult.status !== 0) {
\t\tthrow new Error(`cron run failed (${execResult.status}): ${(execResult.stderr || execResult.stdout || "").trim()}`);
\t}
\tlet runId = "";
\tconst raw = String(execResult.stdout || "").trim();
\ttry {
\t\tconst parsed = JSON.parse(raw);
\t\tif (parsed && typeof parsed.runId === "string") runId = parsed.runId;
\t} catch {}
\treturn { jobName, jobId, runId };
}
async function maybeRouteDiscordIntent(params) {
\tif (!shouldRunIntentRouting(params)) return null;
\tconst promptText = await extractLatestUserTextFromSessionFile(params.sessionFile);
\tif (!promptText) return null;
\ttry {
\t\tlet intent;
\t\tif (shouldOverrideToNewsTask(promptText)) {
\t\t\tintent = "news_task";
\t\t\tlog$16.info(`[intent-router] bypass classifier: news_task (manual cron heuristics)`);
\t\t} else {
\t\t\tintent = await classifyDiscordIntent(promptText);
\t\t}
\t\tif (intent === "chat") return { intent, rerouted: false, promptText };
\t\tconst provider = "openai-codex";
\t\tconst modelId = "gpt-5.4";
\t\tconst model = resolveModelFromRegistry({ modelRegistry: params.modelRegistry, provider, modelId });
\t\tconst route = { intent, rerouted: true, promptText, provider, modelId, model };
\t\tif (intent === "news_task") {
\t\t\tif (isManualNewsRerunPrompt(promptText)) {
\t\t\t\tconst queued = await queueFormalNewsJobRun(promptText);
\t\t\t\troute.messageOverride = `你已经成功触发正式任务 ${queued.jobName}${queued.runId ? `（runId: ${queued.runId}）` : ""}。不要自己生成新闻摘要。不要输出中间过程。只回复这一句：已触发正式任务 ${queued.jobName}，结果将由正式任务单独投递。`;
\t\t\t\troute.manualNewsRun = true;
\t\t\t} else {
\t\t\t\troute.messageOverride = await buildFormalNewsManualPrompt(promptText);
\t\t\t}
\t\t}
\t\treturn route;
\t} catch (error) {
\t\tlog$16.warn(`[intent-router] primary route failed: ${error?.message ?? error}`);
\t\ttry {
\t\t\tif (shouldOverrideToNewsTask(promptText)) {
\t\t\t\tconst provider = "openai-codex";
\t\t\t\tconst modelId = "gpt-5.4";
\t\t\t\tconst model = resolveModelFromRegistry({ modelRegistry: params.modelRegistry, provider, modelId });
\t\t\t\tconst route = { intent: "news_task", rerouted: true, promptText, provider, modelId, model };
\t\t\t\tconst queued = await queueFormalNewsJobRun(promptText);
\t\t\t\troute.messageOverride = `你已经成功触发正式任务 ${queued.jobName}${queued.runId ? `（runId: ${queued.runId}）` : ""}。不要自己生成新闻摘要。不要输出中间过程。只回复这一句：已触发正式任务 ${queued.jobName}，结果将由正式任务单独投递。`;
\t\t\t\troute.manualNewsRun = true;
\t\t\t\tlog$16.info(`[intent-router] catch-path: recovered as news_task`);
\t\t\t\treturn route;
\t\t\t}
\t\t\tconst provider = "openai-codex";
\t\t\tconst modelId = "gpt-5.4";
\t\t\tconst model = resolveModelFromRegistry({ modelRegistry: params.modelRegistry, provider, modelId });
\t\t\tlog$16.info(`[intent-router] fallback to codex (ollama classifier or sub-path failed)`);
\t\t\treturn { intent: "task_control", rerouted: true, promptText, provider, modelId, model };
\t\t} catch (e2) {
\t\t\tlog$16.warn(`[intent-router] codex fallback failed: ${e2?.message ?? e2}`);
\t\t\treturn null;
\t\t}
\t}
}
"""


def main():
    text = TARGET.read_text(encoding="utf-8")
    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)

    start = text.find(START_MARKER)
    end = text.find(END_MARKER, start)
    if start < 0 or end < 0:
        raise SystemExit("current intent router block not found")

    text = text[:start] + NEW_BLOCK + text[end:]
    TARGET.write_text(text, encoding="utf-8")
    print("PATCH_CURRENT_TO_V7_OK")


if __name__ == "__main__":
    main()
