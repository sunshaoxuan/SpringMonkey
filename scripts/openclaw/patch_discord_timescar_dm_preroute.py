#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import shutil
import subprocess


DIST_ROOTS = [
    Path("/var/lib/openclaw/.openclaw/plugin-runtime-deps/openclaw-2026.4.29-4eca5026e977/dist/extensions/discord"),
    Path("/usr/lib/node_modules/openclaw/dist/extensions/discord"),
]

TARGET = "message-handler.process-Pj5ph16g.js"

HELPER = r'''
function isSpringMonkeyTimesCarDmCommand(text) {
	const raw = typeof text === "string" ? text.trim() : "";
	if (!raw) return false;
	if (!/(订车|预约|TimesCar|timescar|开始时间|结束时间|往后延|延[迟时]|改到|后天|明天)/u.test(raw)) return false;
	return /(取消|改|开始时间|结束时间|往后延|延[迟时]|后天|明天|检查|查询|查看|看看|列表|记录|未来)/u.test(raw);
}
async function runSpringMonkeyTimesCarDmCommand(text, messageTimestamp) {
	const { execFile } = await import("node:child_process");
	const script = "/var/lib/openclaw/repos/SpringMonkey/scripts/timescar/timescar_handle_dm_adjust_request.py";
	return await new Promise((resolve) => {
		execFile("python3", [script, "--text", text, "--message-timestamp", messageTimestamp || new Date().toISOString(), "--force"], {
			timeout: 1800000,
			maxBuffer: 1024 * 1024
		}, (error, stdout, stderr) => {
			const output = [stdout, stderr].filter(Boolean).join("\n").trim();
			resolve({
				ok: !error,
				code: error && typeof error.code !== "undefined" ? error.code : 0,
				output: output || (error ? String(error.message || error) : "TimesCar 指令执行完成")
			});
		});
	});
}
async function maybeHandleSpringMonkeyTimesCarDmPreroute(params) {
	if (!params.isDirectMessage) return false;
	if (!isSpringMonkeyTimesCarDmCommand(params.text)) return false;
	const result = await runSpringMonkeyTimesCarDmCommand(params.text, params.messageTimestamp);
	const prefix = result.ok ? "TimesCar 私信任务已由汤猴事件入口完成。" : `TimesCar 私信任务执行失败，退出码：${result.code}`;
	const content = `${prefix}\n${result.output}`.slice(0, 1900);
	await createChannelMessage(params.rest, params.channelId, {
		body: {
			content,
			allowed_mentions: { parse: [] },
			message_reference: {
				message_id: params.messageId,
				fail_if_not_exists: false
			}
		}
	});
	return true;
}
'''

ANCHOR = "async function processDiscordMessage(ctx, observer) {"
INSERT_AFTER = "const text = messageText;\n\tif (!text) {"
INSERT_BLOCK = r'''const text = messageText;
	if (await maybeHandleSpringMonkeyTimesCarDmPreroute({
		isDirectMessage,
		text,
		rest: createDiscordRestClient({
			cfg,
			token,
			accountId
		}).rest,
		channelId: messageChannelId,
		messageId: message.id,
		messageTimestamp: message.timestamp
	})) return;
	if (!text) {'''

OLD_INSERT_BLOCK = r'''const text = messageText;
	if (await maybeHandleSpringMonkeyTimesCarDmPreroute({
		isDirectMessage,
		text,
		rest: createDiscordRestClient({
			cfg,
			token,
			accountId
		}).rest,
		channelId: messageChannelId,
		messageId: message.id
	})) return;
	if (!text) {'''

HELPER_PATTERN = re.compile(
    r"\nfunction isSpringMonkeyTimesCarDmCommand\(text\) \{.*?\nasync function processDiscordMessage\(ctx, observer\) \{",
    re.S,
)


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    changed = False
    helper_replacement = "\n" + HELPER + "\nasync function processDiscordMessage(ctx, observer) {"
    if "maybeHandleSpringMonkeyTimesCarDmPreroute" in text:
        text, count = HELPER_PATTERN.subn(lambda _match: helper_replacement, text, count=1)
        if count:
            changed = True
    else:
        if ANCHOR not in text:
            raise RuntimeError(f"anchor not found in {path}")
        text = text.replace(ANCHOR, helper_replacement.lstrip("\n"), 1)
        changed = True
    if "messageTimestamp: message.timestamp" not in text:
        if OLD_INSERT_BLOCK in text:
            text = text.replace(OLD_INSERT_BLOCK, INSERT_BLOCK, 1)
            changed = True
    if INSERT_BLOCK not in text:
        if INSERT_AFTER not in text:
            raise RuntimeError(f"insert anchor not found in {path}")
        text = text.replace(INSERT_AFTER, INSERT_BLOCK, 1)
        changed = True
    if not changed:
        return False
    backup = path.with_name(f"{path.name}.bak-timescar-dm-preroute-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(path, backup)
    path.write_text(text, encoding="utf-8")
    subprocess.run(["node", "--check", str(path)], check=True, text=True)
    print(f"patched {path} backup={backup}")
    return True


def main() -> int:
    patched_any = False
    for root in DIST_ROOTS:
        path = root / TARGET
        if not path.exists():
            continue
        patched_any = patch_file(path) or patched_any
    if not any((root / TARGET).exists() for root in DIST_ROOTS):
        raise SystemExit("target file not found")
    print("PATCH_DISCORD_TIMESCAR_DM_PREROUTE_OK", "changed" if patched_any else "already-applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
