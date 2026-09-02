# OpenClaw Codex primary model migration

Date: 2026-07-13

## Requirement

Move active OpenClaw primary workloads from the retired GPT-5.5 baseline to the ccnode Codex-compatible endpoint while preserving scheduled jobs, delivery destinations, and reasoning effort.

## Official model contract

Current production OpenClaw configuration uses the explicit `openai-codex/gpt-5.3-codex-spark` model id through `http://ccnode.briconbric.com:49530/v1`. The retired `22545` Ollama/Qwen path is not part of the active fallback chain. Gemini Pro remains a smoke-gated fallback candidate through the same `49530` endpoint and is enabled only after a live chat smoke returns `ok`.

Runtime evidence is recorded in `docs/runtime-notes/openclaw-22545-fallback-retirement-2026-09.md`.

## Repository changes

- Primary OpenClaw route: `openai-codex/gpt-5.3-codex-spark`
- Python fallback client model id: `gpt-5.3-codex-spark`
- Domain implementation runner: `openai-codex/gpt-5.3-codex-spark`
- News orchestrator, worker, and finalizer: `openai-codex/gpt-5.3-codex-spark`
- Generic cron default and XHS recurring contract: `openai-codex/gpt-5.3-codex-spark`
- Gemini Pro fallback is configured only by `scripts/remote_install_gemini_model_fallback.py` after a live smoke test.

## Runtime acceptance

Deployment is accepted only after the ccnode proxy exposes `gpt-5.3-codex-spark`, the OpenClaw auth/profile guard registers it, an owner-DM smoke request succeeds, and recurring jobs pass one gated retry. Public channels must not receive migration tests.

## Rollback

Revert the migration commit, rerun the model auth/profile guard, restore the XHS cron model to `openai-codex/gpt-5.5`, and repeat the owner-DM smoke check.

