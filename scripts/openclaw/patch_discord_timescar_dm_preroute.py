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
async function runSpringMonkeyIntentToolRouter(params) {
	const { execFile } = await import("node:child_process");
	const script = "/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw/intent_tool_router.py";
	return await new Promise((resolve) => {
		execFile("python3", [
			script,
			"--text",
			params.text,
			"--channel",
			"discord_dm",
			"--user-id",
			params.authorId || "unknown",
			"--message-timestamp",
			params.messageTimestamp || new Date().toISOString(),
			"--json"
		], {
			timeout: 1800000,
			maxBuffer: 1024 * 1024
		}, (error, stdout, stderr) => {
			const output = String(stdout || "").trim();
			const diagnostic = String(stderr || "").trim();
			if (diagnostic) {
				console.warn("[springmonkey-intent-tool-router][stderr]", diagnostic.slice(0, 4000));
			}
			resolve({
				ok: !error,
				code: error && typeof error.code !== "undefined" ? error.code : 0,
				output: output || (error ? "OpenClaw intent tool router failed; diagnostics kept in service journal" : "OpenClaw intent tool router completed")
			});
		});
	});
}
function buildSpringMonkeyRouterMessageBody(params, content, withReference = true) {
	const body = {
		content: String(content || "").slice(0, 1900),
		allowed_mentions: { parse: [] }
	};
	if (withReference && params.messageId) {
		body.message_reference = {
			message_id: params.messageId,
			fail_if_not_exists: false
		};
	}
	return body;
}
async function sendSpringMonkeyRouterMessage(params, content) {
	try {
		await createChannelMessage(params.rest, params.channelId, {
			body: buildSpringMonkeyRouterMessageBody(params, content, true)
		});
		return true;
	} catch (err) {
		console.warn("[springmonkey-intent-tool-router][reply-reference-failed]", String(err).slice(0, 1000));
	}
	try {
		await createChannelMessage(params.rest, params.channelId, {
			body: buildSpringMonkeyRouterMessageBody(params, content, false)
		});
		return true;
	} catch (err) {
		console.warn("[springmonkey-intent-tool-router][reply-failed]", String(err).slice(0, 1000));
		return false;
	}
}
function startSpringMonkeyDmLifecycle(params) {
	let stopped = false;
	let ackSent = false;
	const sendTypingSignal = async () => {
		if (stopped) return;
		try {
			await sendTyping({
				rest: params.rest,
				channelId: params.channelId
			});
		} catch (err) {
			console.warn("[springmonkey-intent-tool-router][typing-failed]", String(err).slice(0, 1000));
		}
	};
	void sendTypingSignal();
	const typingTimer = setInterval(() => {
		void sendTypingSignal();
	}, 8000);
	typingTimer.unref?.();
	const ackTimer = setTimeout(() => {
		if (stopped || ackSent) return;
		ackSent = true;
		void sendSpringMonkeyRouterMessage(params, "汤猴已收到私信，正在通过事件入口处理。完成后会继续回复执行结果。");
	}, 4000);
	ackTimer.unref?.();
	return () => {
		stopped = true;
		clearInterval(typingTimer);
		clearTimeout(ackTimer);
	};
}
async function maybeHandleSpringMonkeyIntentToolRouter(params) {
	if (!params.isDirectMessage) return false;
	if (!(typeof params.text === "string") || !params.text.trim()) return false;
	const stopLifecycle = startSpringMonkeyDmLifecycle(params);
	let result = null;
	try {
		result = await runSpringMonkeyIntentToolRouter(params);
	} finally {
		stopLifecycle();
	}
	let payload = null;
	try {
		payload = JSON.parse(result.output || "{}");
	} catch (_error) {}
	if (payload && payload.status === "chat") {
		const chatReply = typeof payload.reply === "string" ? payload.reply.trim() : "";
		if (!chatReply) return false;
		await sendSpringMonkeyRouterMessage(params, chatReply);
		return true;
	}
	const routerReply = payload && typeof payload.reply === "string" ? payload.reply : result.output;
	const prefix = result.ok ? "汤猴私信任务已由通用事件路由处理。" : `汤猴私信任务路由失败，退出码：${result.code}`;
	const content = `${prefix}\n${routerReply}`.slice(0, 1900);
	await sendSpringMonkeyRouterMessage(params, content);
	return true;
}
'''

ANCHOR = "async function processDiscordMessage(ctx, observer) {"
INSERT_AFTER = "const text = messageText;\n\tif (!text) {"
INSERT_BLOCK = r'''const text = messageText;
	if (await maybeHandleSpringMonkeyIntentToolRouter({
		isDirectMessage,
		text,
		rest: createDiscordRestClient({
			cfg,
			token,
			accountId
		}).rest,
		channelId: messageChannelId,
		messageId: message.id,
		messageTimestamp: message.timestamp,
		authorId: message.author?.id
	})) return;
	if (!text) {'''

OLD_TIMESCAR_INSERT = r'''const text = messageText;
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

HELPER_PATTERN = re.compile(
    r"\n(?:function isSpringMonkeyTimesCarDmCommand\(text\) \{.*?|async function runSpringMonkeyIntentToolRouter\(params\) \{.*?)\nasync function processDiscordMessage\(ctx, observer\) \{",
    re.S,
)


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    changed = False
    helper_replacement = "\n" + HELPER + "\nasync function processDiscordMessage(ctx, observer) {"
    if "maybeHandleSpringMonkeyTimesCarDmPreroute" in text or "maybeHandleSpringMonkeyIntentToolRouter" in text:
        text, count = HELPER_PATTERN.subn(lambda _match: helper_replacement, text, count=1)
        if count:
            changed = True
    else:
        if ANCHOR not in text:
            raise RuntimeError(f"anchor not found in {path}")
        text = text.replace(ANCHOR, helper_replacement.lstrip("\n"), 1)
        changed = True

    if OLD_TIMESCAR_INSERT in text:
        text = text.replace(OLD_TIMESCAR_INSERT, INSERT_BLOCK, 1)
        changed = True
    if INSERT_BLOCK not in text:
        if INSERT_AFTER not in text:
            raise RuntimeError(f"insert anchor not found in {path}")
        text = text.replace(INSERT_AFTER, INSERT_BLOCK, 1)
        changed = True
    if not changed:
        return False
    backup = path.with_name(f"{path.name}.bak-intent-tool-router-{datetime.now().strftime('%Y%m%d%H%M%S')}")
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
    print("PATCH_DISCORD_INTENT_TOOL_ROUTER_OK", "changed" if patched_any else "already-applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
