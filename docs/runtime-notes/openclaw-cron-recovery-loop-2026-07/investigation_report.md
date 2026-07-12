# OpenClaw cron recovery loop investigation

## Finding

The previous runtime had three separate mechanisms:

1. `cron_failure_self_heal.py` detected and recorded failures.
2. `agent_society_runtime_record_gap.py` classified gaps and generated repair candidates.
3. `job_orchestrator.py` retried only inside the original process.

The missing production path was a durable owner that continued across timer scans, applied concrete repairs, triggered the original cron job after verification, and reconciled the new official run.

## Implemented flow

`cron_recovery_guard.py` owns a persistent incident state. For every terminal official cron failure it evaluates the cron contract, Gateway Health, Doctor, model runtime, credentials, configuration drift and delivery safety in order. It records every point result, applies bounded repair, calls official `openclaw cron run` by unchanged job ID, and reconciles the returned `runId` on later scans.

The guard performs at most two reruns. Credential blockers, already completed delivery, disabled jobs, failed verification and exhausted attempts remain terminal incidents.

## Safety

The normalized cron contract is fingerprinted before and after recovery. Schedule, delivery target, session, model and fallback changes fail the integrity gate. Public-channel smoke delivery is outside this guard and remains forbidden by migration policy.
