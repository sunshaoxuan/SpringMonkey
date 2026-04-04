# Channel Output Discipline Policy

## Purpose

Operational tasks should not spam the channel with running commentary.

Unless the user explicitly requests real-time progress updates, channel output must stay minimal.

## Default Rule

For task execution in the channel:

- do not continuously post intermediate progress
- send at most one start message
- send at most one completion message
- otherwise, send only the final result

## Realtime Exception

Realtime progress updates are allowed only when the user explicitly asks for live / step-by-step / real-time reporting.

Silence is the default. Live commentary is opt-in.

## Landing Requirement

This rule must live in config and verification, not only in chat memory.

For news workflow changes, keep these layers aligned:

1. `config/news/broadcast.json`
2. `scripts/news/apply_news_config.py`
3. `scripts/news/verify_news_config.py`
4. runtime notes / policies
