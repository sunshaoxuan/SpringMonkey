"""
OpenClaw Discord 新闻手动重跑补丁 v8

根因：v3-v7 的 messageOverride 被设置到 params.message，但 runEmbeddedAttempt
**从不读取 params.message**（它只读 sessionFile）。因此 override 是死代码，
模型始终看到 session 中的原始 Discord 消息 "手动重跑 17:00 新闻播报"，
导致主 chat session 在 cron session 运行流水线的同时自由发挥生成新闻摘要。

用户看到两条消息：
  1. 主 session 的自由摘要（快，几秒内）
  2. cron session 的正确流水线输出（慢，2-3 分钟后）

修复（两步）：
  1. manualNewsRun=true 时设 params.disableTools = true
     → 阻止模型调用 web_fetch/web_search/exec 等工具
  2. 重写 session JSONL 中最后一条 user 消息的内容为 override 指令
     → 模型看到 "你已成功触发正式任务…只回复一句确认" 而不是原始文本

效果：主 session 秒回 "已触发正式新闻任务…请稍候"，cron session 独立执行流水线。

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
\t\tlog$16.info(`[intent-router] intent=${intentRoute.intent} reroute=${params.provider}/${params.modelId}${intentRoute.messageOverride ? " formal-payload=1" : ""}`);
\t} else if (intentRoute?.intent) {
\t\tlog$16.debug(`[intent-router] intent=${intentRoute.intent} keep=${params.provider}/${params.modelId}`);
\t}"""


NEW_BLOCK = """\tif (intentRoute?.rerouted) {
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
