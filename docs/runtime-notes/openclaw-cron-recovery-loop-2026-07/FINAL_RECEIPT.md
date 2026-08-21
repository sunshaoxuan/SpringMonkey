# Final receipt

status: implementation complete, remote activation evidence pending

entrypoint: `scripts/openclaw/cron_failure_self_heal.py`

guard: `scripts/openclaw/cron_recovery_guard.py`

model_gate: `scripts/openclaw/model_runtime_probe.py`

state: `/var/lib/openclaw/.openclaw/workspace/agent_society_kernel/cron_recovery_guard_state.json`

success_contract:

1. Official retry, recurring backoff, in-flight task ownership, Tasks maintenance and Doctor repair execute first.
2. Every remaining failure has ordered point results.
3. Every fallback repair has a verification result.
4. A fresh official state check immediately precedes custom rerun.
5. The original job ID is used for bounded rerun.
6. The new official run is reconciled as recovered, waiting_official, diagnosing, blocked or exhausted.
7. The cron contract fingerprint does not change.

rollback: add `--disable-recovery-guard` to the existing self-heal service while retaining official observation, gap recording, log retention and all existing cron definitions.
