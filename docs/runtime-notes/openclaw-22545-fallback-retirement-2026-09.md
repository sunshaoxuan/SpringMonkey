# OpenClaw 22545 Fallback Retirement

Date: 2026-09-02

## Decision

OpenClaw chat, intent, news, and self-improvement model calls should use the
ccnode OpenAI-compatible endpoint:

```text
http://ccnode.briconbric.com:49530/v1
```

The old Ollama/Qwen fallback on port 22545 is retired for these model calls.

## Evidence

Host checks on 2026-09-02 showed:

- `http://ccnode.briconbric.com:49530/v1/models` is reachable and lists
  `gpt-5.3-codex-spark`, `gpt-5.5`, `gpt-5.3-codex-spark`, and `gpt-image-2`.
- OpenClaw agent smoke with `openai-codex/gpt-5.3-codex-spark` returned `ok`.
- `http://ccnode.briconbric.com:22545/api/tags` timed out or returned an empty
  HTTP reply from client and host checks.
- OpenClaw agent smoke with `ollama/qwen3:14b` failed with a network connection
  error.

## Implementation

- `remote_install_public_model_resources.py` clears `OPENCLAW_MODEL_FALLBACK*`
  and `OPENCLAW_QWEN_FALLBACK*`.
- `remote_install_model_auth_profile_guard.py` removes `ollama` provider
  registration, clears default model fallbacks, and registers 49530 Codex
  models including `gpt-5.3-codex-spark`.
- `model_fallback_client.py` has no fallback by default. Explicit fallback
  requires `OPENCLAW_MODEL_FALLBACK_BASE_URL` and `OPENCLAW_MODEL_FALLBACK`.
- News runtime config clears `chatFallback` and `ollamaBaseUrl`.

## Gemini Pro Candidate

Gemini Pro via the ccnode 49530 OpenAI-compatible endpoint is the preferred
future fallback. The repository includes a smoke-gated installer:

```text
python scripts/remote_install_gemini_model_fallback.py
```

The installer probes `gemini-pro-agent` through `/v1/chat/completions` before
writing runtime fallback config. If the endpoint reports no available accounts,
the installer leaves production fallback disabled.

## Embeddings

The 49530 endpoint was probed for `/v1/embeddings`. At the time of this change,
standard embedding model names were not available through that endpoint. Memory
embedding backend changes therefore require a separate validated provider.

