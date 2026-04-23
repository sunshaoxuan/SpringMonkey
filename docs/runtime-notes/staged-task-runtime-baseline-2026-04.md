# Staged Task Runtime Baseline

Date: 2026-04-23 (Asia/Tokyo)

## Goal

Make multi-step jobs observable before they are fully migrated into the native scheduler.

This is the transition layer for tasks that currently still run as a single `exec`, but are not truly single-step in nature.

## Why This Exists

Some jobs look like one command externally but are multi-step internally:

- TimesCar browser workflows
- weather data collection and report rendering
- news discovery / fetch / worker / merge / finalize / verify pipelines

If they stay black-box:

- the platform only sees one final exit code or one final timeout
- the real failed stage stays hidden
- later self-improvement has no stage-specific failure surface to learn from

## Current Baseline

Repository file:

- `scripts/staged_jobs/task_trace.py`

This lightweight runtime writes per-task trace files under:

- `/var/lib/openclaw/.openclaw/workspace/state/task_traces/<category>/<task>.latest.json`

The trace stores:

- current phase
- ordered steps
- artifacts
- final message

## Current Coverage

### 1. Weather

Repository file:

- `scripts/weather/discord_weather_report.py`

Current staged phases include:

- day-kind decision
- per-location weather fetch
- final report ready

The user-facing stdout stays unchanged as the final weather report text.

### 2. News Pipeline

Repository file:

- `scripts/news/run_news_pipeline.py`

Current staged phases include:

- build plan
- load fetcher
- discover
- fetch
- worker
- merge
- finalize
- verify
- final artifact ready

The pipeline still prints `PIPELINE_OK ...` on success, so existing cron behavior remains compatible.

## Compatibility Rule

This baseline is not yet the native scheduler graph.

It is a compatibility-preserving observability layer.

That means:

- the cron job definition may remain unchanged
- stdout contracts must remain compatible
- but the internal execution should now expose phases and artifacts

## Migration Meaning

This staged runtime is the bridge between:

- black-box multi-step jobs

and

- native scheduler graph jobs

It gives the platform enough structure to later reason about:

- failed phase
- failed tool surface
- retry / rollback decision
- future helper growth
