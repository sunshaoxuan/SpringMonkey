# OpenClaw Failure Layer Model

## Why This Exists

Recent incidents were repeatedly misread because a healthy lower layer was mistaken for a healthy end-to-end system.

Examples:

- LINE push API succeeded, but direct task reply still failed
- a patch script was fixed in Git, but the active host bundle still contained stale code
- a news cron job existed and started, but the qwen timeout retry chain was absent from the active runner

This note defines the current failure layers for the SpringMonkey host.

## Layer 0: Host Liveness

Artifacts:

- `openclaw.service`
- `http://127.0.0.1:18789/healthz`

Failure examples:

- startup guard timeout
- service stuck in startup
- health endpoint unavailable

Pass condition:

- service is `active`
- health endpoint returns live status

## Layer 1: Channel Substrate

Artifacts:

- LINE provider startup
- Discord provider startup
- webhook routing
- provider credentials and secrets

Failure examples:

- LINE webhook accepted nothing
- Discord target mapping was wrong
- provider disconnected

Pass condition:

- provider starts cleanly
- direct outbound push is possible

Important:

This proves transport can send. It does not prove the agent can emit content.

## Layer 2: Active Runtime Artifact

Artifacts:

- `monitor-*.js`
- `selection-*.js`
- `pi-embedded-runner-*.js`

Failure examples:

- patch updated in Git but not present in current host bundle
- installer chose wrong bundle family member
- updater replaced filenames and stale guard logic kept targeting old shapes

Pass condition:

- current active host artifact contains expected markers

## Layer 3: Embedded Run Core

Artifacts:

- qwen timeout retry logic
- compaction route
- overflow handling
- per-run context policy

Failure examples:

- qwen timeout retries absent
- compaction precheck still shaped by stale reserve assumptions
- run reaches prompt start and then stalls

Pass condition:

- run starts under expected model
- expected retry / compaction markers exist
- stale runtime assumptions are not driving immediate failure

## Layer 4: Visible Reply Emission

Artifacts:

- direct ack
- watchdog progress
- no-response fallback

Failure examples:

- LINE only shows loading animation
- model run ends with no visible text
- fallback path exists in theory but never reaches the user

Pass condition:

- a visible response is emitted under the intended chain

Important:

This is separate from transport health. A successful native push test does not validate this layer.

## Layer 5: Task Orchestration

Artifacts:

- cron jobs
- formal news rerun routing
- pipeline worker/finalizer chain
- session reuse and already-running logic

Failure examples:

- `openclaw cron run` returns `already-running`
- worker summarization times out
- final digest never reaches Discord

Pass condition:

- formal job definition is used
- worker stages complete or retry correctly
- final delivery reaches target

## Current Mapping

### LINE Direct Chat

- Layer 0: host liveness
- Layer 1: LINE provider and LINE push API
- Layer 2: `monitor-*.js`
- Layer 3: embedded runner + qwen path
- Layer 4: visible reply emission

### Discord News Digest

- Layer 0: host liveness
- Layer 1: Discord provider and target routing
- Layer 2: `pi-embedded-runner-*.js` and `selection-*.js`
- Layer 3: qwen timeout retry + compaction baseline
- Layer 5: formal cron orchestration + pipeline summarization + final delivery

## Incident Rule

Every incident note should explicitly say:

- the failed layer
- the observed evidence
- the healthy lower layers
- the still-unverified upper layers

Otherwise the same class of issue will keep being rediscovered as if it were new.
