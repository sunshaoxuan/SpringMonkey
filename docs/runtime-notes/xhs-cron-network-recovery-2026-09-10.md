# XHS cron network recovery

Date: 2026-09-10

## Incident

The `xhs-recommendation-every-3-days` job started at 10:00 JST and exhausted four attempts by 10:06. Every attempt failed before content generation with `FailoverError: LLM request failed: network connection error` against the `openai-codex/gpt-5.6-sol` route.

## Runtime evidence

At 19:45 JST the OpenClaw service and the cron job were enabled. Direct host probes to the configured `49530` endpoint succeeded for both `/responses` and `/chat/completions`. This establishes recovery at the time of diagnosis and classifies the morning failure as a transient endpoint connection outage.

The cron failure self-heal timer remained active. Its scans reported zero processed failures because automatic source selection trusted an empty official task list and did not supplement it with journal events. Its recurring backoff threshold also expected five official failures while this runtime stopped after four attempts.

The first manual rerun reached the host after repository deployment and failed before task startup because the recovery command demoted from root to the `openclaw` user. The runtime config is root managed and rejected that read with `EACCES`.

The root managed rerun entered the agent, completed read and browser tool calls, and ended after approximately 103 seconds. The provider had no explicit `timeoutSeconds`, and the outer cron run aborted the next model response at the provider idle timeout. No document write tool was called in that session.

## Repair contract

Automatic scans combine official task failures with journal failures for jobs absent from the official result. The recovery guard takes ownership after four failed official attempts. The XHS capability contract and repair installer use `openai-codex/gpt-5.6-sol`.

Recovery and manual recurring job tools invoke the official cron CLI under their service account. The obsolete `runuser` branch is removed so root managed runtime configuration remains readable.

The `openai-codex` provider registers `gpt-5.6-sol` explicitly and uses a 600 second provider timeout. The XHS job keeps its 3600 second whole-run ceiling.

The first post-timeout-fix acceptance run delegated product research to a child session. That child inherited the global `gpt-5.3-codex-spark` default instead of the cron payload model and repeatedly emitted empty `exec` and `web_fetch` arguments. The XHS cron installer now appends an idempotent current-run-only policy that prohibits `sessions_spawn`, keeping research, browser work, Google Docs writing, verification, and delivery under the configured `gpt-5.6-sol` run.

## Acceptance

Run the cron failure self-heal and recovery guard unit tests. Deploy the repository to the host, reinstall the self-heal timer, manually run the XHS job once, and verify successful completion plus owner DM delivery.

## Rollback

Revert the incident repair commit, redeploy the previous repository revision, and rerun `scripts/remote_install_cron_failure_self_heal.py`.
