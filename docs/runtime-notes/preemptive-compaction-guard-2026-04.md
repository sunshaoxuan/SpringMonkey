# Preemptive Compaction Guard

Date: 2026-04-11 (Asia/Tokyo)

## Goal

Reduce task failures caused by context overflow before the run reaches the hard limit.

## Global compaction baseline

Current host baseline:

- `agents.defaults.compaction.mode = "safeguard"`
- `agents.defaults.compaction.reserveTokens = 12000`
- `agents.defaults.compaction.keepRecentTokens = 8000`
- `agents.defaults.compaction.reserveTokensFloor = 12000`
- `agents.defaults.compaction.recentTurnsPreserve = 6`

## Runtime pre-task guard

The current `pi-embedded` bundle is patched so that before prompt execution:

- if the prompt would already overflow the budget, normal preemptive compaction still applies
- if the prompt is not overflowing yet but is already near the budget, the run preemptively compacts before the task proceeds

Current proactive threshold:

- when message count is at least `48`
- and estimated prompt tokens reach about `90%` of the prompt budget before reserve

the runtime chooses `compact_only` before the task continues.

## Why this exists

OpenClaw already had a pre-prompt compaction framework, but the stock threshold was too conservative.
This guard makes compaction happen before hard overflow for long-lived Discord / LINE task sessions while still leaving room to preserve recent raw turns.
The reserve baseline must still fit the active model context window; for the current `openai-codex/gpt-5.5` primary route use the Codex context baseline, and if the run falls back to `ollama/qwen3:14b`, use the smaller Qwen context baseline.

## Host application

Use:

- `python SpringMonkey/scripts/remote_install_preemptive_compaction_guard.py`

It will:

1. raise the global compaction baseline in `openclaw.json`
2. patch the current `selection-*.js` bundle preemptive compaction threshold
3. restart `openclaw.service`
4. verify `healthz` and LINE webhook
