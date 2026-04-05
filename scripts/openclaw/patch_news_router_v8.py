"""
OpenClaw Discord 新闻手动重跑补丁 v8（修订版）

根因：v3-v7 的 messageOverride 被设到 params.message，但 runEmbeddedAttempt
从不读取 params.message（只读 sessionFile）。session 文件中用户消息由
prewarmSessionFile 在 intent routing 之后写入，故 session 重写也无法命中
当前消息。模型始终看到原始 "手动重跑 17:00 新闻播报"，自由发挥生成摘要。

修复（两步）：
  1. params.disableTools = true → 禁止所有工具调用（web_fetch/exec 等）
  2. params.prompt 覆盖为强制确认指令 → 这是 system/instruction 级别的
     最高优先级上下文，模型在所有 session 消息之前先看到此指令

效果：主 session 秒回确认文本，不生成新闻内容；cron session 独立执行流水线。

前置：dist 中已含 v3-v7 的 intent routing + async spawn 逻辑。
用法：python3 scripts/openclaw/patch_news_router_v8.py && systemctl restart openclaw.service
"""
from pathlib import Path
import shutil


TARGET = Path("/usr/lib/node_modules/openclaw/dist/pi-embedded-BYdcxQ5A.js")
BACKUP = Path(
    "/usr/lib/node_modules/openclaw/dist/pi-embedded-BYdcxQ5A.js.bak-20260406-v8-disable-main-session"
)


OLD_BLOCK = """\tif (intentRoute?.rerouted) {
\t\tparams.provider = intentRoute.provider;
\t\tparams.modelId = intentRoute.modelId;
\t\tparams.model = intentRoute.model;
\t\tif (intentRoute.messageOverride) params.message = intentRoute.messageOverride;
\t\tif (intentRoute.manualNewsRun && params.sessionFile) {
\t\t\tparams.disableTools = true;
\t\t\ttry {
\t\t\t\tconst _raw = await fs.readFile(params.sessionFile, "utf8");
\t\t\t\tconst _lines = _raw.trimEnd().split("\\n");
\t\t\t\tfor (let _i = _lines.length - 1; _i >= 0; _i--) {
\t\t\t\t\ttry {
\t\t\t\t\t\tconst _entry = JSON.parse(_lines[_i]);
\t\t\t\t\t\tif (_entry?.message?.role === "user") {
\t\t\t\t\t\t\tconst _overrideText = intentRoute.messageOverride || "已触发正式新闻任务，结果将由独立任务投递。只回复这一句确认。";
\t\t\t\t\t\t\tif (typeof _entry.message.content === "string") {
\t\t\t\t\t\t\t\t_entry.message.content = _overrideText;
\t\t\t\t\t\t\t} else if (Array.isArray(_entry.message.content)) {
\t\t\t\t\t\t\t\t_entry.message.content = [{ type: "text", text: _overrideText }];
\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t_lines[_i] = JSON.stringify(_entry);
\t\t\t\t\t\t\tbreak;
\t\t\t\t\t\t}
\t\t\t\t\t} catch (_pe) {}
\t\t\t\t}
\t\t\t\tawait fs.writeFile(params.sessionFile, _lines.join("\\n") + "\\n", "utf8");
\t\t\t\tlog$16.info("[intent-router] v8: manual news run \\u2192 tools disabled + session user msg rewritten");
\t\t\t} catch (_e) {
\t\t\t\tlog$16.warn(`[intent-router] v8: session rewrite failed: ${_e?.message ?? _e}`);
\t\t\t}
\t\t}
\t\tlog$16.info(`[intent-router] intent=${intentRoute.intent} reroute=${params.provider}/${params.modelId}${intentRoute.messageOverride ? " formal-payload=1" : ""}${intentRoute.manualNewsRun ? " manual-news-run=1 tools-disabled=1" : ""}`);
\t} else if (intentRoute?.intent) {
\t\tlog$16.debug(`[intent-router] intent=${intentRoute.intent} keep=${params.provider}/${params.modelId}`);
\t}"""


NEW_BLOCK = """\tif (intentRoute?.rerouted) {
\t\tparams.provider = intentRoute.provider;
\t\tparams.modelId = intentRoute.modelId;
\t\tparams.model = intentRoute.model;
\t\tif (intentRoute.messageOverride) params.message = intentRoute.messageOverride;
\t\tif (intentRoute.manualNewsRun) {
\t\t\tparams.disableTools = true;
\t\t\tparams.prompt = "[MANDATORY SYSTEM OVERRIDE — DO NOT IGNORE]\\n\\nA formal news cron job (news-digest-jst-1700) has been successfully triggered and is running in an isolated session. The pipeline is executing independently. Your ONLY job in this turn is to confirm the trigger.\\n\\nRULES (absolute, no exceptions):\\n1. Do NOT generate any news content, summary, or digest.\\n2. Do NOT attempt to fetch RSS feeds, search the web, or run any code.\\n3. Do NOT simulate tool calls in text.\\n4. Respond with EXACTLY this one sentence in Chinese: \\u300c\\u5df2\\u89e6\\u53d1\\u6b63\\u5f0f\\u65b0\\u95fb\\u4efb\\u52a1\\uff0c\\u7ed3\\u679c\\u5c06\\u7531\\u72ec\\u7acb\\u4efb\\u52a1\\u6295\\u9012\\u5230\\u9891\\u9053\\uff0c\\u8bf7\\u7a0d\\u5019\\u3002\\u300d\\n5. Do NOT add any other text before or after that sentence.";
\t\t\tlog$16.info("[intent-router] v8: manual news run \\u2192 tools disabled + prompt overridden");
\t\t}
\t\tlog$16.info(`[intent-router] intent=${intentRoute.intent} reroute=${params.provider}/${params.modelId}${intentRoute.messageOverride ? " formal-payload=1" : ""}${intentRoute.manualNewsRun ? " manual-news-run=1 tools-disabled=1" : ""}`);
\t} else if (intentRoute?.intent) {
\t\tlog$16.debug(`[intent-router] intent=${intentRoute.intent} keep=${params.provider}/${params.modelId}`);
\t}"""


def main():
    text = TARGET.read_text(encoding="utf-8")
    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
    if OLD_BLOCK not in text:
        raise SystemExit(
            "v8 target block not found — dist may already be patched "
            "or v3-v7 layout changed"
        )
    text = text.replace(OLD_BLOCK, NEW_BLOCK, 1)
    TARGET.write_text(text, encoding="utf-8")
    print("PATCH_V8_OK")


if __name__ == "__main__":
    main()
