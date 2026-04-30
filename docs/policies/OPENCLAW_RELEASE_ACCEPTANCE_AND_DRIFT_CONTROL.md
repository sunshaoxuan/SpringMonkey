# OpenClaw Release Acceptance And Drift Control

## Purpose

This policy exists because recent failures were repeatedly caused by the same classes of mistakes:

- repository code changed, but the active host runtime did not
- a patch installer targeted a stale bundle name or stale anchor
- a lower layer was fixed, and that partial success was mistaken for an end-to-end recovery
- a host push path worked, but the agent reply path still failed
- a job existed and even started, but its runtime patch chain was incomplete

The goal is to stop those classes of failures from recurring as "new" incidents.

## Scope

This policy applies to any change that affects:

- `openclaw.service`
- `/var/lib/openclaw/.openclaw/openclaw.json`
- `/var/lib/openclaw/.openclaw/cron/jobs.json`
- `/usr/lib/node_modules/openclaw/dist/*.js`
- LINE / Discord delivery
- runtime guards and startup guards
- compaction and model timeout behavior
- news pipeline and cron execution
- Agent Society runtime / kernel deployment

## Mandatory Rules

1. A local script change is not a fix.
2. A Git commit is not a fix.
3. A successful installer run is not a fix.
4. A fix is only accepted after the current host runtime artifact was verified.
5. A fix is only accepted after a matching smoke test or real chain verification.
6. Never claim "fixed" when only one layer was fixed.
7. Never use push-channel success as proof that agent reply success exists.
8. Never use "job exists" as proof that job execution is healthy.

## Required Release Sequence

Every runtime-affecting change must follow this order:

1. update repository code
2. update repository documentation
3. commit to Git
4. push to remote
5. ensure host repo has pulled the new revision
6. re-run the repo-backed installer or startup guard
7. verify the active host artifact
8. run a targeted smoke test
9. record concrete evidence before claiming completion

## Artifact Selection Discipline

Bundle filenames are not stable across OpenClaw upgrades. Installers and guards must select bundles by content, not by filename alone and not by mtime alone.

Required examples:

- `monitor-*.js` should be chosen by LINE direct-flow markers such as:
  - `received message from `
  - `no response generated`
  - `showLoadingAnimation`
- `selection-*.js` should be chosen by compaction-route markers such as:
  - `promptBudgetBeforeReserve`
  - `proactiveThresholdTokens`
- `pi-embedded-runner-*.js` should be chosen by embedded-runner markers such as:
  - `let timeoutCompactionAttempts = 0;`
  - `derivePromptTokens(lastRunPromptUsage)`
  - `MAX_TIMEOUT_COMPACTION_ATTEMPTS`
  - `const contextOverflowError = !aborted ? (() => {`

Forbidden shortcuts:

- pick the first `pi-embedded-*.js`
- pick only by latest mtime
- assume the same filename survives upstream update

## Mandatory Acceptance Evidence

### 1. Host Health

- `openclaw.service` is `active`
- `http://127.0.0.1:18789/healthz` returns `{"ok":true,"status":"live"}`

### 2. Active Artifact Evidence

Acceptance must include evidence from the current host artifact:

- actual selected bundle path
- current marker present in that active bundle

Examples:

- LINE watchdog:
  - `line_direct_ack`
  - `line_direct_watchdog`
  - `line_no_response_fallback`
- qwen timeout retry:
  - `MAX_OLLAMA_QWEN_TIMEOUT_RETRIES`
  - `[model-timeout-retry]`
  - `currentTimeoutRetryKey`
- preemptive compaction:
  - `const proactiveThresholdTokens = Math.max(1, Math.floor(promptBudgetBeforeReserve * .9));`

### 3. Config Evidence

When the issue relates to compaction or model budget, acceptance must include the current host values from `/var/lib/openclaw/.openclaw/openclaw.json`.

For the current SpringMonkey host baseline:

- `reserveTokens = 12000`
- `reserveTokensFloor = 12000`
- `keepRecentTokens = 8000`
- `recentTurnsPreserve = 6`

### 4. Execution Evidence

Acceptance must include at least one relevant chain:

- LINE direct visible reply chain
- LINE native push chain
- Discord news cron chain
- `openclaw cron run <jobId>` chain

### 5. Negative Evidence

If the bug was a repeated runtime error, acceptance must show that the old error disappeared after redeploy.

Examples:

- no more `TypeError: text?.trim is not a function`
- no more stale bundle selection after upgrade
- no more prompt overflow caused by stale reserve assumptions

## Layered Failure Reporting

Every incident must state:

1. which layer failed
2. which evidence proves the failure
3. which lower layers were verified healthy
4. which upper layers remain unverified

Without this, the same family of bugs will keep being misreported as if nothing was learned.

## Forbidden Claims

Do not claim:

- "LINE is fixed"
- "news is fixed"
- "this is in baseline"
- "host is stable now"

unless the matching end-to-end evidence exists.

Use narrower claims instead:

- "the host LINE push path is healthy"
- "the active monitor bundle now contains the fallback patch"
- "the active embedded runner now contains qwen timeout retry markers"
- "the cron job was re-queued and is currently running"

## Post-Upgrade Minimum

After any OpenClaw upgrade, the following must happen before calling the environment recovered:

1. verify active bundle families again
2. rerun repo-backed runtime installers
3. verify markers in active bundles
4. verify service and health endpoint
5. run at least:
   - one LINE direct smoke test
   - one `openclaw cron run` smoke test
   - one Discord/news verification if news runtime was touched

## Current Environment Notes

Current environment assumptions that must be revalidated after upgrades:

- service: `openclaw.service`
- health endpoint: `http://127.0.0.1:18789/healthz`
- primary model: `openai-codex/gpt-5.5`
- direct channels in active use: LINE and Discord
- current news delivery target: Discord channel `1483636573235843072`
- host repo path: `/var/lib/openclaw/repos/SpringMonkey`

## Delivery Visibility Rule

All task execution reports, failure notices, diagnostics, retry summaries,
internal paths, stderr/stdout excerpts, and blocker explanations must be
delivered only to the owner's Discord private channel `1497009159940608020`.

Public channels may receive only successful final publication results for tasks
that are explicitly public-facing, such as finished news or weather broadcasts.
A failed run must not publish any failure report to public channels.
