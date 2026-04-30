# Qwen Fallback Policy

Date: 2026-04-30 (Asia/Tokyo)

## Goal

OpenClaw defaults are Codex-first. `ollama/qwen3:14b` is a fallback model only
and must not be used as the default primary model for new chat, task-control,
news, cron, routing, delivery, or self-repair behavior.

## Runtime Policy

- Global primary model: `openai-codex/gpt-5.4`
- Global fallback model: `ollama/qwen3:14b`
- News orchestrator, worker, and finalize model default to `openai-codex/gpt-5.4`.
- Qwen/Ollama may be attempted only after the Codex path is unavailable or explicitly rejected by a bounded gate.

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
