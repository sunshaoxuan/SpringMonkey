# OpenClaw Redeployment Runbook 2026

This document summarizes the major 2026 runtime changes for `汤猴` and how to rebuild them after host loss, package overwrite, or fresh provisioning.

Use this together with:

- [CAPABILITY_INDEX.md](/tsclient/C/tmp/default/SpringMonkey/docs/CAPABILITY_INDEX.md)
- [openclaw-runtime-baseline-2026-04.md](/tsclient/C/tmp/default/SpringMonkey/docs/runtime-notes/openclaw-runtime-baseline-2026-04.md)
- [line-runtime-baseline-2026-04.md](/tsclient/C/tmp/default/SpringMonkey/docs/runtime-notes/line-runtime-baseline-2026-04.md)
- [news-task-domain.md](/tsclient/C/tmp/default/SpringMonkey/docs/runtime-notes/news-task-domain.md)

## Scope

This runbook covers the 2026 changes that materially changed runtime behavior:

- shared Discord / LINE capability baseline
- chat model policy
- browser backend and TimesCar automation
- `memory-lancedb` repair and guardrails
- news pipeline and news delivery rules
- Ollama endpoint queuing
- international channel predeployment
- remote recovery scripts and indexing

## Source Of Truth

Authority order remains:

1. live host runtime and active secrets
2. repo scripts and factual runtime notes
3. reports and chat history

Do not treat this repo as a secret store.

## Current Baseline

As of 2026-04-09, the intended baseline is:

- `openclaw.service` runs through `/usr/local/bin/openclaw-gateway-supervise`
- `HOME=/var/lib/openclaw`
- shared env file: `/etc/openclaw/openclaw.env`
- chat primary: `openai-codex/gpt-5.4`
- chat fallback only: `ollama/qwen3:14b`
- Discord and LINE share one gateway and one provider-secret baseline
- browser backend is a persistent Chrome CDP session on `127.0.0.1:18800`
- TimesCar automation should reuse the persistent browser backend instead of launching a fresh Chrome per task
- long-memory backend is `memory-lancedb` with `1024`-dim embeddings and startup guardrails
- news jobs run through `scripts/news/run_news_pipeline.py`
- news freshness requires both timestamp-window filtering and cross-run dedupe

## 2026 Change Ledger

Use this as the compact “what changed this year” map before rebuilding.

| Area | 2026 landing change | Repo truth | Host/runtime landing point |
|------|----------------------|------------|----------------------------|
| Shared capabilities | Discord / LINE now share one provider-secret baseline and one elevated-tool baseline | `scripts/remote_enable_shared_channel_capabilities.py`, `docs/runtime-notes/openclaw-runtime-baseline-2026-04.md` | `/etc/openclaw/openclaw.env`, `openclaw.service` drop-in, `openclaw.json` |
| Chat model policy | Global primary fixed to `openai-codex/gpt-5.4`, Qwen/Ollama only fallback | `docs/runtime-notes/openclaw-runtime-baseline-2026-04.md` | `/var/lib/openclaw/.openclaw/openclaw.json` |
| Browser baseline | Browser tool moved to persistent Chrome CDP backend instead of ad hoc launch | `scripts/remote_enable_persistent_browser_backend.py`, `scripts/remote_install_browser_guardrails.py` | `openclaw-browser-backend.service`, `127.0.0.1:18800` |
| LINE runtime | LINE plugin, webhook, `dmPolicy`, frpc path, and shared-capability boundary were formalized | `docs/runtime-notes/line-runtime-baseline-2026-04.md` | `/var/lib/openclaw/.openclaw/openclaw.json`, `/line/webhook`, frpc mapping |
| Long memory | `memory-lancedb` was repaired to use raw `/v1/embeddings` and guarded at startup | `scripts/openclaw/patch_memory_lancedb_raw_embeddings_current.py`, `scripts/remote_install_memory_lancedb_guard.py` | `memory-lancedb` dist patch, systemd `ExecStartPre/ExecStartPost` guard |
| TimesCar | Site-entry discovery switched from single hardcoded URL to cache-first discovery; task browser path should reuse persistent browser | `docs/runtime-notes/timescar-site-discovery-baseline-2026-04.md` | `~/.openclaw/workspace/TIMESCAR_AUTOMATION.md`, `~/.openclaw/workspace/state/timescar_entry_candidates.json` |
| News delivery | News cron success path must emit only `final_broadcast.md`, not an execution report | `docs/runtime-notes/news-cron-final-broadcast-delivery-fix.md`, `scripts/news/apply_news_config.py` | cron payload written into `openclaw.json` / `jobs.json` |
| News freshness | News now hard-filters by timestamp window and keeps cross-run dedupe state | `scripts/news/news_fetcher.py`, `scripts/news/run_news_pipeline.py`, `config/news/broadcast.json` | `/var/lib/openclaw/.openclaw/state/news/recent_items.json` |
| Generic scheduled tasks | Ordinary recurring jobs now need a real generic cron writer and post-write verification, not conversational promises | `scripts/cron/upsert_generic_cron_job.py`, `docs/runtime-notes/generic-cron-task-domain-2026-04.md` | `/var/lib/openclaw/.openclaw/cron/jobs.json` |
| Ollama scheduling | Same-endpoint model requests were serialized with same-model preference to reduce thrash | `scripts/remote_install_ollama_endpoint_queue.py`, `docs/runtime-notes/ollama-endpoint-model-queue-2026-04.md` | OpenClaw dist patch on host |
| International channels | Non-China-centric channels were predeployed but left uncredentialed by default | `scripts/remote_enable_international_channels.py` | `openclaw.json` plugin/channel entries |
| Recovery tooling | Remote CLI and scenario scripts were added so rebuild no longer depends on ad hoc shell history | `scripts/openclaw_remote_cli.py`, `scripts/INDEX.md`, `docs/ops/TOOLS_REGISTRY.md` | operator workflow |

## Host-State Paths To Preserve

These are the host-side paths that matter even when the repo is intact.

- `/etc/openclaw/openclaw.env`
- `/etc/systemd/system/openclaw.service.d/`
- `/usr/local/lib/openclaw/`
- `/var/lib/openclaw/.openclaw/openclaw.json`
- `/var/lib/openclaw/.openclaw/secrets/`
- `/var/lib/openclaw/.openclaw/state/news/recent_items.json`
- `/var/lib/openclaw/.openclaw/workspace/`
- `/var/lib/openclaw/.openclaw/workspace/state/timescar_entry_candidates.json`
- `/var/lib/openclaw/.openclaw/memory/lancedb`
- `/usr/lib/node_modules/openclaw/dist/`

If the host is rebuilt from scratch, restore these in intent order rather than copying them blindly from an unknown snapshot.

## Redeploy Order

Apply these in order after a rebuild or destructive host event.

### 1. Core OpenClaw Service

- Restore the gateway service shape first.
- Verify `openclaw.service` uses the supervised form, not raw `openclaw gateway run`.
- Confirm `HOME=/var/lib/openclaw`.

Primary references:

- [openclaw-runtime-baseline-2026-04.md](/tsclient/C/tmp/default/SpringMonkey/docs/runtime-notes/openclaw-runtime-baseline-2026-04.md)
- [HOST_ACCESS_REDACTED.md](/tsclient/C/tmp/default/SpringMonkey/docs/ops/HOST_ACCESS_REDACTED.md)

### 2. Pull Repo And Reapply Scripts

- Pull the latest repo onto the host checkout under `/var/lib/openclaw/repos/SpringMonkey`
- Re-run repo-driven apply scripts rather than hand-editing drifted host files

Primary tools:

- [remote_springmonkey_git_pull.py](/tsclient/C/tmp/default/SpringMonkey/scripts/remote_springmonkey_git_pull.py)
- [openclaw_remote_cli.py](/tsclient/C/tmp/default/SpringMonkey/scripts/openclaw_remote_cli.py)
- [INDEX.md](/tsclient/C/tmp/default/SpringMonkey/scripts/INDEX.md)

### 3. Shared Discord / LINE Capability Baseline

- Restore the shared env-file loading on `openclaw.service`
- Ensure both channels are allowed through `tools.elevated.allowFrom`
- Keep channel-specific credentials separate, but provider secrets shared

Primary tools:

- [remote_enable_shared_channel_capabilities.py](/tsclient/C/tmp/default/SpringMonkey/scripts/remote_enable_shared_channel_capabilities.py)
- [line-runtime-baseline-2026-04.md](/tsclient/C/tmp/default/SpringMonkey/docs/runtime-notes/line-runtime-baseline-2026-04.md)

### 4. Chat Model Policy

Hard rule:

- global primary remains `openai-codex/gpt-5.4`
- `ollama/qwen3:14b` is fallback only unless the user explicitly changes policy

Check both repo docs and host runtime before touching task payloads.

Primary references:

- [openclaw-runtime-baseline-2026-04.md](/tsclient/C/tmp/default/SpringMonkey/docs/runtime-notes/openclaw-runtime-baseline-2026-04.md)
- [broadcast.json](/tsclient/C/tmp/default/SpringMonkey/config/news/broadcast.json)

### 5. Browser Backend

Restore the persistent browser backend before any browser-heavy tasks:

- Chrome installed at `/usr/bin/google-chrome`
- persistent CDP backend on `127.0.0.1:18800`
- browser guardrails installed
- browser profile `openclaw` healthy

Primary tools:

- [remote_enable_browser_capabilities.py](/tsclient/C/tmp/default/SpringMonkey/scripts/remote_enable_browser_capabilities.py)
- [remote_enable_persistent_browser_backend.py](/tsclient/C/tmp/default/SpringMonkey/scripts/remote_enable_persistent_browser_backend.py)
- [remote_install_browser_guardrails.py](/tsclient/C/tmp/default/SpringMonkey/scripts/remote_install_browser_guardrails.py)

### 6. TimesCar Automation

Important 2026 rule:

- do not rely on a fresh Playwright-launched Chrome for TimesCar
- reuse the persistent browser backend through CDP
- keep entry discovery cache logic, but do not hardcode a single login URL forever

Primary reference:

- [timescar-site-discovery-baseline-2026-04.md](/tsclient/C/tmp/default/SpringMonkey/docs/runtime-notes/timescar-site-discovery-baseline-2026-04.md)

Operational notes:

- `timescar_secret.sh` must use the absolute key path under `/var/lib/openclaw/.openclaw/secrets/timescar.key`
- task scripts under `~/.openclaw/workspace/scripts/` may diverge from repo copies; reconcile before assuming repo state matches host state

### 7. Long Memory

Restore `memory-lancedb` only after the embedding path is fixed.

Required properties:

- query embeddings and stored vectors must both remain `1024` dimensions
- startup guard must run before `openclaw.service`
- post-start check must validate dimensions

Primary tools:

- [remote_repair_memory_lancedb.py](/tsclient/C/tmp/default/SpringMonkey/scripts/remote_repair_memory_lancedb.py)
- [remote_install_memory_lancedb_guard.py](/tsclient/C/tmp/default/SpringMonkey/scripts/remote_install_memory_lancedb_guard.py)
- [memory-lancedb-raw-embeddings-fix.md](/tsclient/C/tmp/default/SpringMonkey/docs/runtime-notes/memory-lancedb-raw-embeddings-fix.md)

### 8. News Task Domain

Restore the news task domain after core runtime and memory are healthy.

Required 2026 rules:

- news cron jobs run the pipeline wrapper, not ad hoc freeform chat
- success path must emit only `final_broadcast.md` content
- freshness must be enforced mechanically
- recent-item dedupe must be persisted outside the repo checkout

Primary files:

- [broadcast.json](/tsclient/C/tmp/default/SpringMonkey/config/news/broadcast.json)
- [apply_news_config.py](/tsclient/C/tmp/default/SpringMonkey/scripts/news/apply_news_config.py)
- [run_news_pipeline.py](/tsclient/C/tmp/default/SpringMonkey/scripts/news/run_news_pipeline.py)
- [news_fetcher.py](/tsclient/C/tmp/default/SpringMonkey/scripts/news/news_fetcher.py)
- [news-task-domain.md](/tsclient/C/tmp/default/SpringMonkey/docs/runtime-notes/news-task-domain.md)
- [news-cron-final-broadcast-delivery-fix.md](/tsclient/C/tmp/default/SpringMonkey/docs/runtime-notes/news-cron-final-broadcast-delivery-fix.md)

Current 2026 freshness mechanism:

- timestamp-window filtering from RSS / Atom publish timestamps
- optional drop of items without a usable timestamp
- cross-run dedupe cache at `/var/lib/openclaw/.openclaw/state/news/recent_items.json`

### 9. Ollama Endpoint Queue

This is a runtime patch, not a stock feature.

Purpose:

- serialize requests per Ollama endpoint
- prefer same-model requests before switching models on the same endpoint
- reduce model thrash and timeout risk

Primary tools:

- [remote_install_ollama_endpoint_queue.py](/tsclient/C/tmp/default/SpringMonkey/scripts/remote_install_ollama_endpoint_queue.py)
- [ollama-endpoint-model-queue-2026-04.md](/tsclient/C/tmp/default/SpringMonkey/docs/runtime-notes/ollama-endpoint-model-queue-2026-04.md)

### 10. International Channels

These were predeployed in 2026 but not fully credentialed by default.

Meaning:

- plugin availability baseline exists
- actual production use still depends on channel-specific tokens or setup

Primary tool:

- [remote_enable_international_channels.py](/tsclient/C/tmp/default/SpringMonkey/scripts/remote_enable_international_channels.py)

## Validation Checklist

After redeployment, confirm these before declaring recovery complete:

- `openclaw.service` is `active`
- LINE webhook returns `200`
- Discord gateway metrics are healthy
- browser backend reports `running: true`
- `memory-lancedb` logs show recall injection without `256`-dimension errors
- chat primary remains `openai-codex/gpt-5.4`
- TimesCar scripts can complete without launching a fresh browser
- `apply_news_config.py` and `verify_news_config.py` both succeed
- a news pipeline dry run produces `PIPELINE_OK`

## Known 2026 Pitfalls

- `openclaw cron` CLI currently emits a noisy `slack/contract-api.js` config-read stack. This is not yet the primary blocker, but it pollutes diagnostics.
- Runtime task scripts in `~/.openclaw/workspace/scripts/` may drift from repo scripts. For recovery, reconcile host reality, not repo assumptions.
- Browser and TimesCar failures can look like “GPU problems” even when LLM execution is healthy.
- A cron job can report `delivered` while the content is still wrong if the prompt contract is wrong. Delivery success is not business success.

## Recovery Principle

When in doubt:

1. restore service shape
2. restore shared capability baseline
3. restore browser and memory guardrails
4. reapply repo-driven task-domain config
5. validate with one real task per domain

Do not skip directly to “looks active” checks. The 2026 failures were mostly caused by drift between active runtime, patched dist files, and repo documentation.
