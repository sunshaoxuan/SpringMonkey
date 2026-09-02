# Qwen Fallback Policy

Date: 2026-04-30 (Asia/Tokyo)

## Goal

OpenClaw defaults are Codex-first. This historical Qwen fallback policy has
been superseded by the 2026-09 runtime baseline. `ollama/qwen3:14b` must not be
used as the default primary model or active fallback for new chat, task-control,
news, cron, routing, delivery, or self-repair behavior.

## Runtime Policy

- Global primary model: `openai-codex/gpt-5.3-codex-spark`
- Global model endpoint: `http://ccnode.briconbric.com:49530/v1`, the frpc mapping to sub2api at `192.168.20.54:62342`
- Global fallback model: empty unless a smoke-gated fallback installer enables one
- News orchestrator, worker, and finalize model default to `openai-codex/gpt-5.3-codex-spark`.
- Qwen/Ollama should not be attempted in the active chat fallback path.

## Legacy Qwen-First Paths

Older qwen-first timeout retry patches and cron payloads are migration targets.
They are not the default policy anymore. If a legacy job still has:

- `model = ollama/qwen3:14b`
- qwen timeout retry before Codex
- comments saying Codex is disaster-only fallback

then update that path to Codex primary and Qwen fallback through Git, then let
the host obtain it through the approved repo pull path.

## Host Application

Do not hand-edit the host to change this policy. Use Git-delivered config,
scripts, and installers, then verify with:

```bash
python scripts/openclaw_behavior_rule_gate.py --verify-remote-pull
```
