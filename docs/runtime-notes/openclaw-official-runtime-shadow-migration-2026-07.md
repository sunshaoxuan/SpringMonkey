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
6. Owner-DM reporting accepts structured object or array tool output and extracts user-facing text, preventing JSON punctuation such as `], ]` from replacing deployment evidence.
7. `cron_recovery_guard.py` uses official cron state as its control plane. It reads `openclaw cron list --json`, waits while an official task is active, preserves official one-shot retry budgets, and waits for recurring error backoff to reach its maximum tier before SpringMonkey can take ownership.
8. Immediately before any custom rerun, the guard refreshes `openclaw cron show <job> --json` and `openclaw tasks list --runtime cron --json`. A new official run, retry slot, or imminent scheduled run returns the incident to `waiting_official`.
9. Official `tasks maintenance --apply` owns lost-task reconciliation. Official `doctor --fix --non-interactive` owns supported Gateway and configuration repair. SpringMonkey service restart, legacy repair, real model probe, capability repair and bounded rerun are fallback extensions after official handling is unavailable or insufficient.
10. Recovery permits at most two SpringMonkey reruns per job incident. Credential blockers, already-delivered runs, disabled or missing jobs, failed verification, and exhausted attempts stop automatic replay and remain visible in the incident state. Multiple official retry task IDs for one job collapse into one recovery generation.
11. The recovery guard compares the normalized cron contract before and after repair and replay. Any change to job identity, enabled state, schedule, delivery, session, model or fallback fails the recovery integrity gate.
12. The bridge performs no task mutation and no message delivery.
13. `openclaw-long-task-supervisor.timer` and every existing cron definition remain active during the shadow phase.
14. The existing cron-failure timer also writes the shadow snapshot after each scan, so repository auto-sync can activate the phase without changing systemd or waiting for a separate timer installation.

Official behavior reference: OpenClaw commit `26731eb403c680ea4c6da0be67331a9b3c421493` documents three one-shot transient retries, recurring 30s/60s/5m/15m/60m backoff, task reconciliation, cron watchdogs, model fallback/preflight and Doctor repair.

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
