"""
OpenClaw Discord 意图路由补丁 v4（在 v3 基础上）

根因：网关进程以 systemd User=openclaw 运行，非 root。v2/v3 中 queueFormalNewsJobRun 使用
`runuser -u openclaw ...`，在非 root 下会失败：`runuser: may not be used by non-root users`，
异常被 maybeRouteDiscordIntent catch 后返回 null，汤猴退回默认模型自由发挥。

修复：若 process.getuid()===0 则保留 runuser；否则直接 spawnSync("openclaw", ["cron","run",jobId], { env: { ...process.env, HOME: "/var/lib/openclaw" } })。

前置：dist 中已是 v3 路由块（与 patch_news_router_v3.py 的 NEW_ROUTER 一致）。

用法（网关宿主机 root）：
  python3 scripts/openclaw/patch_news_router_v4.py && systemctl restart openclaw.service
"""
from pathlib import Path
import shutil


TARGET = Path("/usr/lib/node_modules/openclaw/dist/pi-embedded-BYdcxQ5A.js")
BACKUP = Path(
    "/usr/lib/node_modules/openclaw/dist/pi-embedded-BYdcxQ5A.js.bak-20260405-news-task-cron-norunuser"
)


# 与 patch_news_router_v3.py 中 NEW_ROUTER 完全一致（当前已部署在宿主机上的块）
OLD_ROUTER = """function selectFormalNewsJobName(promptText) {
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
\tconst result = spawnSync(\"runuser\", [\"-u\", \"openclaw\", \"--\", \"env\", \"HOME=/var/lib/openclaw\", \"openclaw\", \"cron\", \"run\", jobId], { encoding: \"utf8\", timeout: 120000 });
\tif (result.error) throw result.error;
\tif (result.status !== 0) {
\t\tthrow new Error(`cron run failed (${result.status}): ${(result.stderr || result.stdout || \"\").trim()}`);
\t}
\tlet runId = \"\";
\tconst raw = String(result.stdout || \"\").trim();
\ttry {
\t\tconst parsed = JSON.parse(raw);
\t\tif (parsed && typeof parsed.runId === \"string\") runId = parsed.runId;
\t} catch {}
\treturn { jobName, jobId, runId };
}
async function maybeRouteDiscordIntent(params) {
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


NEW_ROUTER = """function selectFormalNewsJobName(promptText) {
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
\tlet result;
\tif (typeof process.getuid === \"function\" && process.getuid() === 0) {
\t\tresult = spawnSync(\"runuser\", [\"-u\", \"openclaw\", \"--\", \"env\", \"HOME=/var/lib/openclaw\", \"openclaw\", \"cron\", \"run\", jobId], { encoding: \"utf8\", timeout: 120000, env });
\t} else {
\t\tresult = spawnSync(\"openclaw\", [\"cron\", \"run\", jobId], { encoding: \"utf8\", timeout: 120000, env });
\t}
\tif (result.error) throw result.error;
\tif (result.status !== 0) {
\t\tthrow new Error(`cron run failed (${result.status}): ${(result.stderr || result.stdout || \"\").trim()}`);
\t}
\tlet runId = \"\";
\tconst raw = String(result.stdout || \"\").trim();
\ttry {
\t\tconst parsed = JSON.parse(raw);
\t\tif (parsed && typeof parsed.runId === \"string\") runId = parsed.runId;
\t} catch {}
\treturn { jobName, jobId, runId };
}
async function maybeRouteDiscordIntent(params) {
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


def main():
    text = TARGET.read_text(encoding="utf-8")
    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
    if OLD_ROUTER not in text:
        raise SystemExit(
            "v3 router block not found — apply patch_news_router_v3.py first, or dist layout changed"
        )
    text = text.replace(OLD_ROUTER, NEW_ROUTER, 1)
    TARGET.write_text(text, encoding="utf-8")
    print("PATCH_V4_OK")


if __name__ == "__main__":
    main()
