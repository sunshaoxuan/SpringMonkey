"""
OpenClaw Discord 意图路由 / 模型降级补丁 v6（在 v5 已部署的基础上）

问题：
1. classifyDiscordIntent 的 fetch 无超时，Ollama 挂死时长时间阻塞或最终失败。
2. maybeRouteDiscordIntent 的 catch 直接 return null，不会自动切到 Codex。
3. 路由未改 provider 时 embedded 仍用 ollama，若 generate 挂死仍无输出。

修复：
1. classifyDiscordIntent：12s AbortController 超时。
2. maybeRouteDiscordIntent：catch 内先尝试与主路径相同的新闻任务恢复；否则 reroute 到 openai-codex/gpt-5.4（task_control）。
3. runEmbeddedAttempt：Discord + 仍为 ollama 时，对 22545 做一次极短 generate 探针（12s，num_predict:1），失败则切 Codex。

前置：dist 已与 v5 一致（bypass classifier 的 maybeRoute + 无超时的 classify）。

用法：
  python3 scripts/openclaw/patch_news_router_v6.py && systemctl restart openclaw.service
"""
from pathlib import Path
import shutil


TARGET = Path("/usr/lib/node_modules/openclaw/dist/pi-embedded-BYdcxQ5A.js")
BACKUP = Path(
    "/usr/lib/node_modules/openclaw/dist/pi-embedded-BYdcxQ5A.js.bak-20260405-ollama-codex-fallback"
)


# v5 部署后的 classify（无 signal）
OLD_CLASSIFY = """async function classifyDiscordIntent(promptText) {
\tconst response = await fetch("http://ccnode.briconbric.com:22545/api/generate", {
\t\tmethod: "POST",
\t\theaders: { "content-type": "application/json" },
\t\tbody: JSON.stringify({
\t\t\tmodel: "qwen3:14b",
\t\t\tprompt: [
\t\t\t\t"Classify the user's intent into exactly one label.",
\t\t\t\t"Allowed labels: chat, task_control, news_task, repo_sync.",
\t\t\t\t"Definitions:",
\t\t\t\t"- chat: normal conversation, questions, explanations, introductions, brainstorming.",
\t\t\t\t"- task_control: change settings, apply/verify/restart/reload/execute/inspect tasks or services, memory ingestion, version checks, maintenance.",
\t\t\t\t"- news_task: rerun/generate/publish/test a news broadcast or news digest.",
\t\t\t\t"- repo_sync: write, commit, push, sync docs/config/work products to git/repo.",
\t\t\t\t"Return JSON only in the form {\\\"intent\\\":\\\"<label>\\\"}.",
\t\t\t\t"User message:",
\t\t\t\tpromptText,
\t\t\t\t"JSON:"
\t\t\t].join("\\n"),
\t\t\tstream: false,
\t\t\tkeep_alive: "8h",
\t\t\toptions: { temperature: 0 }
\t\t})
\t});
\tif (!response.ok) throw new Error(`intent classifier http ${response.status}`);
\tconst data = await response.json();
\tconst raw = String(data?.response ?? "").trim();
\tconst jsonStart = raw.indexOf("{");
\tconst jsonEnd = raw.lastIndexOf("}");
\tconst parsed = JSON.parse(jsonStart >= 0 && jsonEnd > jsonStart ? raw.slice(jsonStart, jsonEnd + 1) : raw);
\tconst intent = typeof parsed?.intent === "string" ? parsed.intent.trim() : "";
\tif (intent === "chat" || intent === "task_control" || intent === "news_task" || intent === "repo_sync") return intent;
\tthrow new Error(`invalid intent classifier label: ${raw}`);
}"""


NEW_CLASSIFY = """async function classifyDiscordIntent(promptText) {
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
}"""


# v5 部署后的 maybeRoute（catch return null）
OLD_MAYBE_ROUTE = """async function maybeRouteDiscordIntent(params) {
\tif (!shouldRunIntentRouting(params)) return null;
\tconst promptText = await extractLatestUserTextFromSessionFile(params.sessionFile);
\tif (!promptText) return null;
\ttry {
\t\tlet intent;
\t\tif (shouldOverrideToNewsTask(promptText)) {
\t\t\tintent = \"news_task\";
\t\t\tlog$16.info(`[intent-router] bypass classifier: news_task (manual cron heuristics)`);
\t\t} else {
\t\t\tintent = await classifyDiscordIntent(promptText);
\t\t}
\t\tif (intent === \"chat\") return { intent, rerouted: false, promptText };
\t\tconst provider = \"openai-codex\";
\t\tconst modelId = \"gpt-5.4\";
\t\tconst model = resolveModelFromRegistry({ modelRegistry: params.modelRegistry, provider, modelId });
\t\tconst route = { intent, rerouted: true, promptText, provider, modelId, model };
\t\tif (intent === \"news_task\") {
\t\t\tif (isManualNewsRerunPrompt(promptText)) {
\t\t\t\tconst queued = await queueFormalNewsJobRun(promptText);
\t\t\t\troute.messageOverride = `你已经成功触发正式任务 ${queued.jobName}${queued.runId ? `（runId: ${queued.runId}）` : \"\"}。不要自己生成新闻摘要。不要输出中间过程。只回复这一句：已触发正式任务 ${queued.jobName}，结果将由正式任务单独投递。`;
\t\t\t\troute.manualNewsRun = true;
\t\t\t} else {
\t\t\t\troute.messageOverride = await buildFormalNewsManualPrompt(promptText);
\t\t\t}
\t\t}
\t\treturn route;
\t} catch (error) {
\t\tlog$16.warn(`[intent-router] classify failed: ${error?.message ?? error}`);
\t\treturn null;
\t}
}"""


NEW_MAYBE_ROUTE = """async function maybeRouteDiscordIntent(params) {
\tif (!shouldRunIntentRouting(params)) return null;
\tconst promptText = await extractLatestUserTextFromSessionFile(params.sessionFile);
\tif (!promptText) return null;
\ttry {
\t\tlet intent;
\t\tif (shouldOverrideToNewsTask(promptText)) {
\t\t\tintent = \"news_task\";
\t\t\tlog$16.info(`[intent-router] bypass classifier: news_task (manual cron heuristics)`);
\t\t} else {
\t\t\tintent = await classifyDiscordIntent(promptText);
\t\t}
\t\tif (intent === \"chat\") return { intent, rerouted: false, promptText };
\t\tconst provider = \"openai-codex\";
\t\tconst modelId = \"gpt-5.4\";
\t\tconst model = resolveModelFromRegistry({ modelRegistry: params.modelRegistry, provider, modelId });
\t\tconst route = { intent, rerouted: true, promptText, provider, modelId, model };
\t\tif (intent === \"news_task\") {
\t\t\tif (isManualNewsRerunPrompt(promptText)) {
\t\t\t\tconst queued = await queueFormalNewsJobRun(promptText);
\t\t\t\troute.messageOverride = `你已经成功触发正式任务 ${queued.jobName}${queued.runId ? `（runId: ${queued.runId}）` : \"\"}。不要自己生成新闻摘要。不要输出中间过程。只回复这一句：已触发正式任务 ${queued.jobName}，结果将由正式任务单独投递。`;
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
\t\t\t\tconst provider = \"openai-codex\";
\t\t\t\tconst modelId = \"gpt-5.4\";
\t\t\t\tconst model = resolveModelFromRegistry({ modelRegistry: params.modelRegistry, provider, modelId });
\t\t\t\tconst route = { intent: \"news_task\", rerouted: true, promptText, provider, modelId, model };
\t\t\t\tif (isManualNewsRerunPrompt(promptText)) {
\t\t\t\t\tconst queued = await queueFormalNewsJobRun(promptText);
\t\t\t\t\troute.messageOverride = `你已经成功触发正式任务 ${queued.jobName}${queued.runId ? `（runId: ${queued.runId}）` : \"\"}。不要自己生成新闻摘要。不要输出中间过程。只回复这一句：已触发正式任务 ${queued.jobName}，结果将由正式任务单独投递。`;
\t\t\t\t\troute.manualNewsRun = true;
\t\t\t\t} else {
\t\t\t\t\troute.messageOverride = await buildFormalNewsManualPrompt(promptText);
\t\t\t\t}
\t\t\t\tlog$16.info(`[intent-router] catch-path: recovered as news_task`);
\t\t\t\treturn route;
\t\t\t}
\t\t\tconst provider = \"openai-codex\";
\t\t\tconst modelId = \"gpt-5.4\";
\t\t\tconst model = resolveModelFromRegistry({ modelRegistry: params.modelRegistry, provider, modelId });
\t\t\tlog$16.info(`[intent-router] fallback to codex (ollama classifier or sub-path failed)`);
\t\t\treturn { intent: \"task_control\", rerouted: true, promptText, provider, modelId, model };
\t\t} catch (e2) {
\t\t\tlog$16.warn(`[intent-router] codex fallback failed: ${e2?.message ?? e2}`);
\t\t\treturn null;
\t\t}
\t}
}"""


OLD_EMBEDDED_INTENT_BLOCK = """\tlog$16.debug(`embedded run start: runId=${params.runId} sessionId=${params.sessionId} provider=${params.provider} model=${params.modelId} thinking=${params.thinkLevel} messageChannel=${params.messageChannel ?? params.messageProvider ?? "unknown"}`);
\tconst intentRoute = await maybeRouteDiscordIntent(params);
\tif (intentRoute?.rerouted) {
\t\tparams.provider = intentRoute.provider;
\t\tparams.modelId = intentRoute.modelId;
\t\tparams.model = intentRoute.model;
\t\tif (intentRoute.messageOverride) params.message = intentRoute.messageOverride;
\t\tlog$16.info(`[intent-router] intent=${intentRoute.intent} reroute=${params.provider}/${params.modelId}${intentRoute.messageOverride ? " formal-payload=1" : ""}${intentRoute.manualNewsRun ? " manual-cron-run=1" : ""}`);
\t} else if (intentRoute?.intent) {
\t\tlog$16.debug(`[intent-router] intent=${intentRoute.intent} keep=${params.provider}/${params.modelId}`);
\t}

\tawait fs.mkdir(resolvedWorkspace, { recursive: true });"""


NEW_EMBEDDED_INTENT_BLOCK = """\tlog$16.debug(`embedded run start: runId=${params.runId} sessionId=${params.sessionId} provider=${params.provider} model=${params.modelId} thinking=${params.thinkLevel} messageChannel=${params.messageChannel ?? params.messageProvider ?? "unknown"}`);
\tconst intentRoute = await maybeRouteDiscordIntent(params);
\tif (intentRoute?.rerouted) {
\t\tparams.provider = intentRoute.provider;
\t\tparams.modelId = intentRoute.modelId;
\t\tparams.model = intentRoute.model;
\t\tif (intentRoute.messageOverride) params.message = intentRoute.messageOverride;
\t\tlog$16.info(`[intent-router] intent=${intentRoute.intent} reroute=${params.provider}/${params.modelId}${intentRoute.messageOverride ? " formal-payload=1" : ""}${intentRoute.manualNewsRun ? " manual-cron-run=1" : ""}`);
\t} else if (intentRoute?.intent) {
\t\tlog$16.debug(`[intent-router] intent=${intentRoute.intent} keep=${params.provider}/${params.modelId}`);
\t}
\tif ((!intentRoute || !intentRoute.rerouted) && String(params.provider ?? "").toLowerCase() === "ollama" && shouldRunIntentRouting(params)) {
\t\tlet ollamaOk = false;
\t\tconst probeModel = String(params.modelId || "qwen3:14b");
\t\tconst ac2 = new AbortController();
\t\tconst tid2 = setTimeout(() => ac2.abort(), 12000);
\t\ttry {
\t\t\tconst pr = await fetch("http://ccnode.briconbric.com:22545/api/generate", {
\t\t\t\tmethod: "POST",
\t\t\t\theaders: { "content-type": "application/json" },
\t\t\t\tsignal: ac2.signal,
\t\t\t\tbody: JSON.stringify({ model: probeModel, prompt: ".", stream: false, options: { num_predict: 1, temperature: 0 } })
\t\t\t});
\t\t\tollamaOk = pr.ok;
\t\t} catch {
\t\t\tollamaOk = false;
\t\t} finally {
\t\t\tclearTimeout(tid2);
\t\t}
\t\tif (!ollamaOk) {
\t\t\tparams.provider = "openai-codex";
\t\t\tparams.modelId = "gpt-5.4";
\t\t\tparams.model = resolveModelFromRegistry({ modelRegistry: params.modelRegistry, provider: "openai-codex", modelId: "gpt-5.4" });
\t\t\tlog$16.warn(`[model-fallback] ollama generate probe failed; switched embedded run to openai-codex/gpt-5.4`);
\t\t}
\t}

\tawait fs.mkdir(resolvedWorkspace, { recursive: true });"""


def main():
    text = TARGET.read_text(encoding="utf-8")
    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
    for label, old, new in (
        ("classifyDiscordIntent", OLD_CLASSIFY, NEW_CLASSIFY),
        ("maybeRouteDiscordIntent", OLD_MAYBE_ROUTE, NEW_MAYBE_ROUTE),
        ("runEmbeddedAttempt intent block", OLD_EMBEDDED_INTENT_BLOCK, NEW_EMBEDDED_INTENT_BLOCK),
    ):
        if old not in text:
            raise SystemExit(f"missing block: {label} — expected v5 + current dist layout")
        text = text.replace(old, new, 1)
    TARGET.write_text(text, encoding="utf-8")
    print("PATCH_V6_OK")


if __name__ == "__main__":
    main()
