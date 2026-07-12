# Final receipt

status: implementation complete, remote activation evidence pending

entrypoint: `scripts/openclaw/cron_failure_self_heal.py`

guard: `scripts/openclaw/cron_recovery_guard.py`

model_gate: `scripts/openclaw/model_runtime_probe.py`

state: `/var/lib/openclaw/.openclaw/workspace/agent_society_kernel/cron_recovery_guard_state.json`

success_contract:

1. Every failure has ordered point results.
2. Every automatic repair has a verification result.
3. The original job ID is used for bounded rerun.
4. The new official run is reconciled as recovered, diagnosing, blocked or exhausted.
5. The cron contract fingerprint does not change.

rollback: add `--disable-recovery-guard` to the existing self-heal service while retaining official observation, gap recording, log retention and all existing cron definitions.
