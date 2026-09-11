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

The next acceptance run stayed in the configured parent model but failed at 21:54 JST with a context overflow after approximately eleven minutes. The model registration already provides a 196k context window. The task policy now bounds research to eight product or image source fetches and twelve browser snapshots, prohibits full-page text dumps, limits failed-page retries to one, and requires immediate Google Docs authoring once the product and three required images are verified.

During deployment verification, the FRP SSH endpoint repeatedly rejected new protocol banners. A read-only connection attempt to the documented Tailscale SSH endpoint displayed an additional authentication URL. The attempt was stopped immediately, and no Tailscale authentication, device, or exposure state was changed. Verification resumed through the existing FRP endpoint after its connection gate cleared.

## Acceptance

The repository was deployed at commit `ee500df`, `openclaw.service` was active, and the installed XHS payload reported model `openai-codex/gpt-5.6-sol`, a 3600 second whole-run timeout, and the current-run-only policy marker.

The final acceptance run `aa1c6f47-c022-49a1-8b12-590b5d33f0c4` started at 22:33 JST and completed at 22:52 JST in 1,124,152 ms. It made no `sessions_spawn` call, created and verified a Google Docs draft with the requested copy, tags, two official product images, and one local review image, then delivered the result to Discord. Final cron state was `ok`, `lastDeliveryStatus` was `delivered`, `lastDelivered` was true, `consecutiveErrors` was zero, and no context-overflow diagnostic remained.

The delivered draft is [XHS-推荐文-2026-09-10-オイコス蛋白咖啡拿铁](https://docs.google.com/document/d/1AcpsZN_vz5i0DdsKEUd8FCGiKdmlpEKLu4VPRhxbjNQ/edit?tab=t.0). It remains a review draft and was not published to Xiaohongshu.

## Owner access policy

Generated Google Docs must be shared directly with the configured `OPENCLAW_OWNER_GOOGLE_EMAIL` account as Viewer before delivery. The task must reopen sharing settings and verify the exact account and role. Public link sharing, edit access, and ownership transfer are outside this workflow. The artifact access follow-up tool uses the same host-side profile so access repairs do not depend on prior chat context.

## Rollback

Revert commits `ee500df`, `5361edb`, `d4ffdbe`, `41580eb`, and `c64dede` as applicable, redeploy the selected repository revision, and rerun `scripts/remote_install_cron_failure_self_heal.py`.
