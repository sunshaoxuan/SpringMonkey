# OpenClaw Current Environment Baseline

## Host

- service: `openclaw.service`
- health endpoint: `http://127.0.0.1:18789/healthz`
- host repo path: `/var/lib/openclaw/repos/SpringMonkey`
- workspace root: `/var/lib/openclaw/.openclaw/workspace`

## Primary Runtime Assumptions

- primary task model: `openai-codex/gpt-5.5`
- direct channels currently in active use:
  - LINE
  - Discord

## Compaction Baseline

Expected current host values:

- `agents.defaults.compaction.mode = safeguard`
- `reserveTokens = 12000`
- `reserveTokensFloor = 12000`
- `keepRecentTokens = 8000`
- `recentTurnsPreserve = 6`

Preemptive compaction rule:

- trigger when estimated prompt usage reaches `90%` of `promptBudgetBeforeReserve`
- preserve recent raw turns instead of replacing everything immediately

## Active Runtime Patch Families

### LINE Direct Visibility

Artifact family:

- `monitor-*.js`

Expected behavior:

- direct ack for direct chat
- watchdog progress update for long-running tasks
- no-response fallback text when the run ends without user-visible content

### Preemptive Compaction

Artifact family:

- `selection-*.js`

Expected behavior:

- proactive compaction route activates before overflow
- threshold is based on current prompt budget

### Embedded Run / Qwen Fallback

Artifact family:

- `pi-embedded-runner-*.js`

Expected behavior:

- `openai-codex/gpt-5.5` is primary; `qwen3:14b` is fallback only
- retry markers exist in the active runner

### Agent Society Runtime

Deployment chain:

- runtime guard from repo
- startup guard from repo
- workspace bridge docs under `/var/lib/openclaw/.openclaw/workspace`

Expected behavior:

- direct task handling can be constrained by goal / intent / task / step guidance
- deployment survives restart through repo-backed startup guards

## Channel Baseline

### LINE

- direct user interaction is active
- native LINE push must be treated as a separate testable layer
- native push success does not prove direct task reply success

### Discord

- public delivery path is active
- current news delivery target: `1483636573235843072`

## News Baseline

Source of truth:

- host config:
  - `/var/lib/openclaw/repos/SpringMonkey/config/news/broadcast.json`
- host jobs:
  - `/var/lib/openclaw/.openclaw/cron/jobs.json`

Expected jobs:

- `news-digest-jst-0900`
- `news-digest-jst-1700`

Expected current properties:

- default model = `openai-codex/gpt-5.5`; fallback model = `ollama/qwen3:14b`
- `timeoutSeconds = 7200`
- execution mode is pipeline
- final delivery target is Discord

## Required Verification After Relevant Changes

### If LINE direct runtime changed

Verify:

- service health
- active `monitor-*.js` markers
- one native LINE push smoke test
- one direct-reply smoke test

### If compaction runtime changed

Verify:

- host compaction values
- active `selection-*.js` markers
- no stale oversized reserve values

### If qwen timeout behavior or news runtime changed

Verify:

- active `pi-embedded-runner-*.js` retry markers
- expected news job timeout values
- one `openclaw cron run <jobId>` verification path or equivalent evidence

## Operational Warning

This is environment-specific. It documents what is true for the current SpringMonkey host, not a universal OpenClaw baseline.
