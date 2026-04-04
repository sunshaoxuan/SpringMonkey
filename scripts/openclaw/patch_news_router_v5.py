"""
OpenClaw Discord 意图路由补丁 v5（在 v4 基础上）

根因：maybeRouteDiscordIntent 先 await classifyDiscordIntent()，而分类器对 Ollama 发 HTTP。
Ollama 卡住/超时时，整段 try 失败 → catch 返回 null → 不调 Codex、不排队 cron，网关仍按默认
provider（多为 ollama）自由发挥。

修复：若 shouldOverrideToNewsTask(promptText) 为真，**跳过分类器**，直接 intent=news_task，
再走 queueFormalNewsJobRun（仅依赖本机 spawnSync + jobs.json，不依赖 Ollama）。

前置：dist 中已是 v4 完整 INTENT ROUTER 块（与 patch_news_router_v4.py 的 NEW_ROUTER 一致）。

用法（网关宿主机 root）：
  python3 scripts/openclaw/patch_news_router_v5.py && systemctl restart openclaw.service
"""
from pathlib import Path
import shutil


TARGET = Path("/usr/lib/node_modules/openclaw/dist/pi-embedded-BYdcxQ5A.js")
BACKUP = Path(
    "/usr/lib/node_modules/openclaw/dist/pi-embedded-BYdcxQ5A.js.bak-20260405-news-bypass-classifier"
)


OLD_MAYBE_ROUTE = """async function maybeRouteDiscordIntent(params) {
\tif (!shouldRunIntentRouting(params)) return null;
\tconst promptText = await extractLatestUserTextFromSessionFile(params.sessionFile);
\tif (!promptText) return null;
\ttry {
\t\tconst rawIntent = await classifyDiscordIntent(promptText);
\t\tlet intent = rawIntent;
\t\tif ((intent === \"chat\" || intent === \"task_control\") && shouldOverrideToNewsTask(promptText)) {
\t\t\tintent = \"news_task\";
\t\t\tlog$16.info(`[intent-router] override ${rawIntent} -> news_task (manual cron run heuristics)`);
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
\t\tlog$16.warn(`[intent-router] classify failed: ${error?.message ?? error}`);
\t\treturn null;
\t}
}"""


def main():
    text = TARGET.read_text(encoding="utf-8")
    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
    if OLD_MAYBE_ROUTE not in text:
        raise SystemExit(
            "v4 maybeRouteDiscordIntent block not found — apply patch_news_router_v4.py first"
        )
    text = text.replace(OLD_MAYBE_ROUTE, NEW_MAYBE_ROUTE, 1)
    TARGET.write_text(text, encoding="utf-8")
    print("PATCH_V5_OK")


if __name__ == "__main__":
    main()
