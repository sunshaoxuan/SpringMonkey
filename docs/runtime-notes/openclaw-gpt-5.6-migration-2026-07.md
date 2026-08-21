# OpenClaw GPT-5.6 migration

Date: 2026-07-13

## Requirement

Move active OpenClaw primary workloads from GPT-5.5 to GPT-5.6 while preserving scheduled jobs, delivery destinations, reasoning effort, and the Qwen fallback.

## Official model contract

OpenAI documents `gpt-5.6` as an alias that currently routes to `gpt-5.6-sol`. The Codex model guide identifies `gpt-5.6-sol` as the default Power model. Production OpenClaw configuration therefore uses the explicit Sol model id. Existing GPT-5.5 reasoning effort should remain the migration baseline.

Sources: <https://developers.openai.com/api/docs/guides/latest-model.md> and <https://developers.openai.com/codex/models>

## Repository changes

- Primary OpenClaw route: `openai-codex/gpt-5.6-sol`
- Python fallback client model id: `gpt-5.6-sol`
- Domain implementation runner: `openai-codex/gpt-5.6-sol`
- News orchestrator, worker, and finalizer: `openai-codex/gpt-5.6-sol`
- Generic cron default and XHS recurring contract: `openai-codex/gpt-5.6-sol`
- Existing `ollama/qwen3:14b` fallback remains unchanged.

## Runtime acceptance

Deployment is accepted only after the ccnode proxy exposes GPT-5.6, the OpenClaw auth/profile guard registers it, an owner-DM smoke request succeeds, and the XHS task completes exactly one gated retry. Public channels must not receive migration tests.

## Rollback

Revert the migration commit, rerun the model auth/profile guard, restore the XHS cron model to `openai-codex/gpt-5.5`, and repeat the owner-DM smoke check.
