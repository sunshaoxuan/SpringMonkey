#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil


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
	return /(取消|改|开始时间|结束时间|往后延|延[迟时]|后天|明天)/u.test(raw);
}
async function maybeHandleSpringMonkeyTimesCarDmPreroute(params) {
	if (!params.isDirectMessage) return false;
	if (!isSpringMonkeyTimesCarDmCommand(params.text)) return false;
	const content = [
		"已收到 TimesCar 预约变更指令，并已由 Discord Gateway 事件入口识别。",
		"当前处理状态：不会再进入通用长流程静默等待。",
		"安全边界：这是会修改真实订单的写操作；在专用改单执行器和确认页校验完成前，本次不自动提交预约变更。"
	].join("\n");
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
		messageId: message.id
	})) return;
	if (!text) {'''


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    changed = False
    if "maybeHandleSpringMonkeyTimesCarDmPreroute" not in text:
        if ANCHOR not in text:
            raise RuntimeError(f"anchor not found in {path}")
        text = text.replace(ANCHOR, HELPER + "\n" + ANCHOR, 1)
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
