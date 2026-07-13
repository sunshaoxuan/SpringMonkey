# OpenClaw GPT-5.6 migration

Date: 2026-07-13

## Requirement

Move active OpenClaw primary workloads from GPT-5.5 to GPT-5.6 while preserving scheduled jobs, delivery destinations, reasoning effort, and the Qwen fallback.

## Official model contract

OpenAI documents `gpt-5.6` as the stable alias for the GPT-5.6 flagship model. The alias currently routes to `gpt-5.6-sol`. Existing GPT-5.5 reasoning effort should remain the migration baseline.

Source: <https://developers.openai.com/api/docs/guides/latest-model.md>

## Repository changes

- Primary OpenClaw route: `openai-codex/gpt-5.6`
- Python fallback client model id: `gpt-5.6`
- Domain implementation runner: `openai-codex/gpt-5.6`
- News orchestrator, worker, and finalizer: `openai-codex/gpt-5.6`
- Generic cron default and XHS recurring contract: `openai-codex/gpt-5.6`
- Existing `ollama/qwen3:14b` fallback remains unchanged.

## Runtime acceptance

Deployment is accepted only after the ccnode proxy exposes GPT-5.6, the OpenClaw auth/profile guard registers it, an owner-DM smoke request succeeds, and the XHS task completes exactly one gated retry. Public channels must not receive migration tests.

## Rollback

Revert the migration commit, rerun the model auth/profile guard, restore the XHS cron model to `openai-codex/gpt-5.5`, and repeat the owner-DM smoke check.
