# Preemptive Compaction Guard

Date: 2026-04-11 (Asia/Tokyo)

## Goal

Reduce task failures caused by context overflow before the run reaches the hard limit.

## Global compaction baseline

Current host baseline:

- `agents.defaults.compaction.mode = "safeguard"`
- `agents.defaults.compaction.reserveTokens = 42000`
- `agents.defaults.compaction.keepRecentTokens = 8000`
- `agents.defaults.compaction.reserveTokensFloor = 32000`
- `agents.defaults.compaction.recentTurnsPreserve = 6`

## Runtime pre-task guard

The current `pi-embedded` bundle is patched so that before prompt execution:

- if the prompt would already overflow the budget, normal preemptive compaction still applies
- if the prompt is not overflowing yet but is already near the budget, the run preemptively compacts before the task proceeds

Current proactive threshold:

- when message count is at least `48`
- and estimated prompt tokens reach about `82%` of the prompt budget before reserve

the runtime chooses `compact_only` before the task continues.

## Why this exists

OpenClaw already had a pre-prompt compaction framework, but the stock threshold was too conservative.
This guard makes compaction happen earlier for long-lived Discord / LINE task sessions.

## Host application

Use:

- `python SpringMonkey/scripts/remote_install_preemptive_compaction_guard.py`

It will:

1. raise the global compaction baseline in `openclaw.json`
2. patch the current `pi-embedded-*.js` bundle preemptive compaction threshold
3. restart `openclaw.service`
4. verify `healthz` and LINE webhook
