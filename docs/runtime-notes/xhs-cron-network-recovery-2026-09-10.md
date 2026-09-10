# XHS cron network recovery

Date: 2026-09-10

## Incident

The `xhs-recommendation-every-3-days` job started at 10:00 JST and exhausted four attempts by 10:06. Every attempt failed before content generation with `FailoverError: LLM request failed: network connection error` against the `openai-codex/gpt-5.6-sol` route.

## Runtime evidence

At 19:45 JST the OpenClaw service and the cron job were enabled. Direct host probes to the configured `49530` endpoint succeeded for both `/responses` and `/chat/completions`. This establishes recovery at the time of diagnosis and classifies the morning failure as a transient endpoint connection outage.

The cron failure self-heal timer remained active. Its scans reported zero processed failures because automatic source selection trusted an empty official task list and did not supplement it with journal events. Its recurring backoff threshold also expected five official failures while this runtime stopped after four attempts.

The first manual rerun reached the host after repository deployment and failed before task startup because the recovery command demoted from root to the `openclaw` user. The runtime config is root managed and rejected that read with `EACCES`.

## Repair contract

Automatic scans combine official task failures with journal failures for jobs absent from the official result. The recovery guard takes ownership after four failed official attempts. The XHS capability contract and repair installer use `openai-codex/gpt-5.6-sol`.

Recovery and manual recurring job tools invoke the official cron CLI under their service account. The obsolete `runuser` branch is removed so root managed runtime configuration remains readable.

## Acceptance

Run the cron failure self-heal and recovery guard unit tests. Deploy the repository to the host, reinstall the self-heal timer, manually run the XHS job once, and verify successful completion plus owner DM delivery.

## Rollback

Revert the incident repair commit, redeploy the previous repository revision, and rerun `scripts/remote_install_cron_failure_self_heal.py`.
