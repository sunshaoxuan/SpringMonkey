from __future__ import annotations

import sys
from pathlib import Path


HELPER = r"""const OLLAMA_ENDPOINT_QUEUES = new Map();
function pickNextOllamaQueuedTask(state) {
	if (!state.pending.length) return null;
	const preferredModel = state.currentModel;
	if (preferredModel) {
		const idx = state.pending.findIndex((entry) => entry.modelKey === preferredModel);
		if (idx >= 0) return state.pending.splice(idx, 1)[0];
	}
	return state.pending.shift() ?? null;
}
function scheduleOllamaEndpointQueue(endpointKey) {
	const state = OLLAMA_ENDPOINT_QUEUES.get(endpointKey);
	if (!state || state.running) return;
	const next = pickNextOllamaQueuedTask(state);
	if (!next) {
		state.currentModel = null;
		OLLAMA_ENDPOINT_QUEUES.delete(endpointKey);
		return;
	}
	state.running = true;
	state.currentModel = next.modelKey;
	queueMicrotask(() => {
		Promise.resolve().then(next.task).catch(() => {
		}).finally(() => {
			next.resolve();
			const latest = OLLAMA_ENDPOINT_QUEUES.get(endpointKey);
			if (!latest) return;
			latest.running = false;
			if (!latest.pending.length) latest.currentModel = null;
			scheduleOllamaEndpointQueue(endpointKey);
		});
	});
}
function enqueueOllamaEndpointTask(endpointKey, modelKey, task) {
	let state = OLLAMA_ENDPOINT_QUEUES.get(endpointKey);
	if (!state) {
		state = { running: false, currentModel: null, pending: [] };
		OLLAMA_ENDPOINT_QUEUES.set(endpointKey, state);
	}
	return new Promise((resolve) => {
		state.pending.push({ modelKey, task, resolve });
		scheduleOllamaEndpointQueue(endpointKey);
	});
}
"""


def main() -> int:
    target = Path("/usr/lib/node_modules/openclaw/dist/stream-DqNCFbiN.js")
    if not target.is_file():
        print(f"missing target: {target}", file=sys.stderr)
        return 1
    text = target.read_text(encoding="utf-8")
    anchor = "function createOllamaStreamFn(baseUrl, defaultHeaders) {"
    if anchor not in text:
        print("missing anchor", file=sys.stderr)
        return 1
    if HELPER not in text:
        text = text.replace(anchor, HELPER + "\n" + anchor, 1)
    old = "\t\tqueueMicrotask(() => void run());\n\t\treturn stream;"
    new = (
        '\t\tconst endpointQueueKey = chatUrl;\n'
        '\t\tconst modelQueueKey = String(model.id || "");\n'
        "\t\tvoid enqueueOllamaEndpointTask(endpointQueueKey, modelQueueKey, run);\n"
        "\t\treturn stream;"
    )
    if old not in text:
        print("missing queueMicrotask target", file=sys.stderr)
        return 1
    text = text.replace(old, new, 1)
    backup = target.with_name(target.name + ".bak-ollama-model-queue")
    backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    target.write_text(text, encoding="utf-8")
    print(f"patched {target}")
    print(f"backup {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
