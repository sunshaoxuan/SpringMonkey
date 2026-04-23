# TimesCar Task Runtime Baseline

Date: 2026-04-23 (Asia/Tokyo)

## Goal

Stop treating TimesCar tasks as black-box single-step scripts when their real execution path is:

1. open website
2. check or establish login state
3. navigate to the correct reservation view
4. inspect current reservation state
5. submit or extend a reservation
6. verify the result

## Why This Exists

The old cron jobs looked like simple `exec` tasks because the cron payload only ran one Python file.

In reality, the important TimesCar jobs were multi-step browser tasks with multiple failure points.

When they failed as black boxes:

- the platform only saw a final timeout or one final error string
- the real failed stage was hidden
- helper / toolsmith growth had no stage-specific failure surface to learn from

## Current Repo-First Baseline

The TimesCar task scripts are now source-controlled in:

- `scripts/timescar/`

The host installer is:

- `scripts/remote_install_timescar_task_runtime.py`

It copies the repo scripts into:

- `/var/lib/openclaw/.openclaw/workspace/scripts/`

This keeps existing cron job definitions stable while replacing the underlying scripts with source-controlled versions.

## Current Runtime Shape

The new baseline introduces:

- `task_runtime.py`
- `timescar_task_guard.py`
- repo-managed versions of:
  - `timescar_fetch_reservations.py`
  - `timescar_next24h_notice.py`
  - `timescar_book_sat_3weeks.py`
  - `timescar_extend_sun_3weeks.py`
  - `timescar_daily_report_render.py`

## Trace Output

Each task now writes a latest trace file under:

- `/var/lib/openclaw/.openclaw/workspace/state/timescar_traces/*.latest.json`

The trace includes:

- job name
- run id
- current phase
- final status
- final message
- ordered step records

This makes the scripts internally multi-step and observable even when the outer cron job still executes them as a single command.

## Compatibility Constraint

User-facing stdout stays compatible with the existing cron jobs.

That means:

- reminders still return `NO_REPLY` or the same reminder message
- daily report still returns report text only
- booking / extension tasks still return the final success or failure text expected by the current delivery chain

The change is internal observability and source control, not a forced cron schema rewrite.

## Migration Implication

This is a transition layer.

It does not yet make TimesCar cron jobs first-class scheduler graph jobs.

But it does remove the worst black-box behavior and exposes stage-level failure surfaces so later self-improvement and scheduler migration have real task structure to work with.
