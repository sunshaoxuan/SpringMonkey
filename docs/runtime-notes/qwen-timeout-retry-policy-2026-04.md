# Qwen Timeout Retry Policy

Date: 2026-04-11 (Asia/Tokyo)

## Goal

For qwen-first tasks, do not fall back to `openai-codex/gpt-5.4` after a single timeout.

## Runtime policy

- Global primary model remains `ollama/qwen3:14b`
- Global fallback remains `openai-codex/gpt-5.4`
- For embedded runs on `ollama/qwen3:14b`:
  - the same model is retried up to 3 total attempts on timeout
  - only after those timeout retries are exhausted may normal model fallback proceed

## Cron timeout baseline

All cron jobs whose payload model is `ollama/qwen3:14b` should use at least:

- `timeoutSeconds = 1800`

This avoids false failures when qwen is healthy but slow.

## Host application

Use:

- `scripts/remote_install_qwen_timeout_retry_policy.py`

It performs:

1. Patch current `pi-embedded-*.js` bundle with qwen timeout retry logic
2. Raise existing qwen cron payload timeouts to `1800`
3. Restart `openclaw.service`
4. Verify host health and resulting qwen cron timeout values

## Notes

- This policy does not change the global model order.
- It only changes timeout handling behavior before fallback.
