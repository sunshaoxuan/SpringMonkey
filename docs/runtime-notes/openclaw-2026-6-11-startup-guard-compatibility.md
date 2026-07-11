# OpenClaw 2026.6.11 startup guard compatibility

Date: 2026-07-12

## Incident

After OpenClaw changed its generated runtime and memory plugin layout, the local agent society patch could no longer find its previous JavaScript anchor. The startup guard returned a failure from `ExecStartPre`, so systemd restarted the gateway every five seconds before the main process could start.

## Requirement change

Runtime patch drift must be reported as a degraded capability. It must not block the OpenClaw gateway from starting. The systemd drop-in also marks the custom guard as non-blocking.

The guard still fails for missing repository scripts, kernel bootstrap failures, and verification failures after a patch reports success. These conditions indicate a broken local deployment rather than an upstream layout change.

## Verification

1. The guard records an explicit compatibility warning when the runtime patch cannot be applied.
2. The gateway continues through startup.
3. The service becomes active and remains stable.
4. Model and channel checks run only after the gateway process is available.

## Model authentication migration

OpenClaw 2026.6.11 stores active authentication state in the agent SQLite database. The previous JSON-only auth guard can therefore report success while the active database contains no profiles. The ccnode credential is a proxy credential and does not use the official OpenAI `sk` format, so the interactive OpenAI key importer rejects it.

Register `openai-codex` as a custom `openai-completions` provider backed by `http://ccnode.briconbric.com:49530/v1`. Keep `openai-codex/gpt-5.5` as the primary model and retain `ollama/qwen3:14b` as the first fallback. This keeps existing cron payloads and runtime policy identifiers stable while separating the ccnode proxy from the official `openai` provider.

## Rollback

Restore the previous guard script and systemd drop-in from version control, then run `systemctl daemon-reload` and restart `openclaw.service`.
