# OpenClaw cron recovery loop investigation

## Finding

The previous runtime had three separate mechanisms:

1. `cron_failure_self_heal.py` detected and recorded failures.
2. `agent_society_runtime_record_gap.py` classified gaps and generated repair candidates.
3. `job_orchestrator.py` retried only inside the original process.

The missing production path was a durable owner that continued across timer scans, applied concrete repairs, triggered the original cron job after verification, and reconciled the new official run.

## Implemented flow

`cron_recovery_guard.py` owns a persistent incident state while OpenClaw remains the primary runtime owner. It reads official cron status and retry state, waits through official retry and backoff, delegates lost reconciliation to Tasks maintenance, delegates supported repair to Doctor, then evaluates the remaining cron contract, Gateway Health, model runtime, credentials, configuration drift and delivery safety.

SpringMonkey calls official `openclaw cron run` only after official ownership is exhausted and a fresh pre-rerun check proves that no official run or imminent retry slot exists. It reconciles the returned `runId` on later scans.

The guard performs at most two custom reruns per job generation. Multiple official task IDs for the same failing job collapse into that single generation. Credential blockers, already completed delivery, disabled jobs, failed verification and exhausted attempts remain terminal incidents.

## Safety

The normalized cron contract is fingerprinted before and after recovery. Schedule, delivery target, session, model and fallback changes fail the integrity gate. Public-channel smoke delivery is outside this guard and remains forbidden by migration policy.
