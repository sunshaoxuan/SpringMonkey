# OpenClaw Sub2API Qwen fallback investigation

Date: 2026-09-11 JST

## Question

Why did TangHou stop with `intent model unavailable or invalid IntentFrame` instead of using the Qwen model exposed by Sub2API?

## Findings

Production had no configured fallback. `/etc/openclaw/openclaw.env` contained empty `OPENCLAW_MODEL_FALLBACK_BASE_URL` and `OPENCLAW_MODEL_FALLBACK`, while both OpenClaw configs had an empty `agents.defaults.model.fallbacks` list.

The failing request reached the primary `gpt-5.3-codex-spark` route twice and received HTTP 503. The dispatcher then returned the non-execution report shown to the owner.

The intent code parsed `OPENCLAW_INTENT_FALLBACK_MODELS` but never consumed that list. The generic fallback client only changed models when the HTTP call failed. A successful HTTP response containing malformed intent JSON therefore also bypassed fallback.

The shared resource installer treated every model name containing `qwen` as the retired Ollama route. This erased a valid Sub2API Qwen model even when its endpoint was 49530. The model auth guard also reset global fallbacks to an empty list after service start.

## Selected repair

Use the exact live model ID `hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S` through the existing 49530 OpenAI-compatible endpoint. Keep the retired 22545 Ollama route disabled.

The intent agent now retries explicit fallback models after both transport errors and invalid `IntentFrame` responses. Qwen receives a separate 180 second timeout because the full 43,598-character production intent prompt took approximately 98 seconds in the live smoke.

Intent validation now rejects missing schema keys and malformed tool candidates, parses the first JSON object without consuming trailing braces, and treats explicit null optional containers as empty containers. Fallback credentials are resolved only from dedicated variables or files, so a missing fallback credential cannot leak the primary provider credential to another endpoint.

The Qwen installer requires exact catalog visibility and a valid strict intent frame before it writes configuration. The startup auth guard only enables the global Qwen fallback when the smoke-gated environment points to the exact model on 49530.

The installer materializes the runtime key file with service-readable permissions, atomically replaces the environment file, invokes the guard with only the two required variables, restarts the service, and verifies every existing OpenClaw config path.

## Acceptance

Local tests passed. On the Linux target, release preflight and 141 tests passed before installation. Commit `d9baadc` was deployed, the service remained active, both configs retained the Qwen fallback, and forced primary failures succeeded through the intent and generic fallback paths. The original external write request was not replayed as part of this infrastructure acceptance.
