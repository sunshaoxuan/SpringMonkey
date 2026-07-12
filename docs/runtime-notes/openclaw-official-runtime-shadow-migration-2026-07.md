# OpenClaw official runtime shadow migration

Date: 2026-07-12

## Goal

Move SpringMonkey runtime observation toward official OpenClaw Tasks, Task audit, Doctor, and Health while preserving every existing cron job, timer, schedule, delivery target, and user-visible behavior.

## Phase 1 behavior

1. `cron_failure_self_heal.py` reads `openclaw tasks list --runtime cron --json` first.
2. Journal parsing remains available as an automatic compatibility fallback.
3. Official `taskId`, `runId`, and `parentFlowId` are persisted with capability-gap evidence.
4. Retained historical failures older than 15 minutes are ignored during the source transition, preventing old task rows from being learned again.
5. `official_runtime_shadow_bridge.py` captures Tasks, Task audit, Doctor, Health, and the complete cron contract fingerprint.
6. The bridge performs no task mutation and no message delivery.
7. `openclaw-long-task-supervisor.timer` and every existing cron definition remain active during the shadow phase.
8. The existing cron-failure timer also writes the shadow snapshot after each scan, so repository auto-sync can activate the phase without changing systemd or waiting for a separate timer installation.

## Delivery safety

Migration tests may use Discord owner DM channel `1497009159940608020` only.

Discord public channel `1483636573235843072` is forbidden for migration test delivery.

The shadow bridge never sends messages. A later live delivery smoke must read `config/openclaw/official_runtime_migration.json` and reject public targets before sending.

## Cron integrity gate

The shadow service hashes the normalized cron contract before and after each probe. The contract includes job identity, enabled state, schedule, delivery, session target, session key, payload model, and payload fallbacks.

Deployment fails when probing changes the contract. The raw jobs file hash is also compared before and after the installer runs.

## Rollback

Disable and remove `openclaw-official-runtime-shadow.timer` and its service. Existing cron jobs, cron failure self-heal, and long-task supervisor continue unchanged.

To restore journal-only failure collection, reinstall the previous `openclaw-cron-failure-self-heal.service` definition or add `--source journal`.

## Next phase gate

Retiring a legacy supervisor requires all of the following:

1. Official task records match cron run outcomes across a full recurring-job cycle.
2. Task completion delivery is verified through owner Discord DM only.
3. No duplicate execution or duplicate delivery is observed.
4. Doctor and Health remain available after Gateway restart.
5. The cron contract fingerprint remains stable.
