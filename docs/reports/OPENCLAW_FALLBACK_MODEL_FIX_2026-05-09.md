# OpenClaw Fallback Model Fix

Date: 2026-05-09 (Asia/Tokyo)

## Symptom

When the primary model (`openai-codex/gpt-5.5`) exhausted its quota (port 49530),
the fallback routing silently failed and the gateway became unresponsive.
Users observed no AI replies from TangHou even though the ccnode Ollama service
(port 22545) was running normally.

## Root Cause

`agents.defaults.model.fallbacks` in `openclaw.json` referenced two model IDs
that do not exist on the ccnode Ollama endpoint:

```
"ollama/qwen3.5-long:latest"   ← not available on ccnode:22545
"ollama/qwen3-long:latest"     ← not available on ccnode:22545
```

When the primary model failed, OpenClaw attempted the listed fallbacks in order,
received 404 / model-not-found from the Ollama API for both, and surfaced no
reply. The `openai-codex` backstop was never reached because the Ollama provider
was tried and errored first.

## Fix Applied

Replaced the two invalid fallback IDs with models confirmed present via
`GET http://ccnode.briconbric.com:22545/api/tags`:

```diff
-  "fallbacks": ["ollama/qwen3.5-long:latest", "ollama/qwen3-long:latest"]
+  "fallbacks": ["ollama/qwen3:14b", "ollama/qwen2.5:14b-instruct"]
```

Also cleaned up the corresponding `agents.defaults.models` allowlist to match.

### File Modified (on host)

- `/var/lib/openclaw/.openclaw/openclaw.json`
  - `agents.defaults.model.fallbacks`
  - `agents.defaults.models`

## Verification

`systemctl restart openclaw.service` was run after the config upload.
Service came up as `active (running)` within 3 seconds.

The effective fallback chain after this fix:

| Priority | Model | Endpoint |
|----------|-------|----------|
| 1 (primary) | `openai-codex/gpt-5.5` | codex cloud |
| 2 (fallback 1) | `ollama/qwen3:14b` | ccnode:22545 |
| 3 (fallback 2) | `ollama/qwen2.5:14b-instruct` | ccnode:22545 |

## Notes

- The valid model list on ccnode changes over time. When adding or removing
  models via `ollama pull` / `ollama rm`, remember to sync `openclaw.json`
  fallbacks accordingly.
- `openclaw.json` is NOT stored in this repo (it contains bot tokens). This
  report is the audit trail. Use `scripts/remote_repair_openclaw_gateway_config.py`
  as a reference for future automated repairs.
