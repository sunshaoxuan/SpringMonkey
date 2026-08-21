# Evidence index

| Claim | Evidence | Confidence | Limitation |
|---|---|---|---|
| Previous watcher only recorded failures | `scripts/openclaw/cron_failure_self_heal.py` before this change | high | Remote active copy not read in this session |
| Original orchestrator retry was process-local | `scripts/openclaw/job_orchestrator.py` | high | Applies to jobs already wrapped by that orchestrator |
| New guard persists cross-scan incidents | `scripts/openclaw/cron_recovery_guard.py` and `test_guard_persists_incident_state` | high | Remote state file still requires host verification |
| Official retry/backoff remains primary | `official_handoff_decision`, `test_official_recurring_backoff_owns_failure_before_saturation`, official cron docs at commit `26731eb` | high | Host OpenClaw version must expose the documented state fields |
| Pre-rerun refresh prevents overlap | `refresh_official_handoff` and `test_pre_rerun_refresh_blocks_when_official_run_started` | high | Fixture execution |
| Official retry task IDs collapse per job | `newest_failure_events` and `test_official_retry_failures_collapse_to_latest_event_per_job` | high | Fixture execution |
| Failed rerun advances to a second bounded attempt | `test_failed_rerun_is_repaired_and_driven_to_second_attempt` | high | Fixture execution |
| Model failures require a real primary-or-fallback call | `scripts/openclaw/model_runtime_probe.py` | high | Live provider probe requires host environment |
| Cron definitions remain unchanged | normalized contract comparison in `cron_failure_self_heal.py` | high | Remote fingerprint still requires host verification |
