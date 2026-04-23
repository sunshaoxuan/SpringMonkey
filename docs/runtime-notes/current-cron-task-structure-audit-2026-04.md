# Current Cron Task Structure Audit

Date: 2026-04-23 (Asia/Tokyo)

## Goal

Inspect current cron jobs by their actual execution structure instead of trusting the outer `exec` shape.

This audit answers:

- which jobs are truly simple
- which jobs are black-box multi-step
- which jobs are already made observable

## Source Of Truth Used

- latest local recovery bundle:
  - `var/recovery-bundles/openclaw-recovery-20260423-042008.tar.gz`
- current repo task scripts under:
  - `scripts/timescar/`
  - `scripts/weather/`
  - `scripts/news/`

## Classification Rules

### A. True single-step

One local computation or rendering step with no external state machine.

### B. Multi-step but still externally wrapped

The cron job still calls one script via `exec`, but the script itself contains multiple real stages.

### C. Already observable staged task

The task exposes phases / steps / artifacts through staged trace or task trace.

## Current Jobs

### 1. `news-digest-jst-0900`

- delivery: `discord`
- current script: `scripts/news/run_news_pipeline.py`
- actual structure: multi-step
- current state: **C**

Observed stages:

- build plan
- discover
- fetch
- worker
- merge
- finalize
- verify

Current note:

- still externally one cron run
- internally now staged and observable

### 2. `news-digest-jst-1700`

- delivery: `discord`
- current script: `scripts/news/run_news_pipeline.py`
- actual structure: multi-step
- current state: **C**

Same staged structure as the 09:00 job.

### 3. `weather-report-jst-0700`

- delivery: `discord`
- current script: `scripts/weather/discord_weather_report.py`
- actual structure: multi-step dataflow
- current state: **C**

Observed stages:

- day-kind decision
- per-location fetch
- final report ready

### 4. `timescar-daily-report-2200`

- delivery: `line`
- current script: `scripts/timescar/timescar_daily_report_render.py`
- actual structure: multi-step via reservation fetch path
- current state: **C**

Reason:

- the outer report renderer is simple
- but it now depends on the staged reservation fetch path

### 5. `timescar-book-sat-3weeks`

- delivery: `line`
- current script: `scripts/timescar/timescar_book_sat_3weeks.py`
- actual structure: browser workflow, clearly multi-step
- current state: **C**

Observed stages include:

- load credentials
- check existing reservation
- open booking page
- validate booking form
- submit booking
- verify result

### 6. `timescar-extend-sun-3weeks`

- delivery: `line`
- current script: `scripts/timescar/timescar_extend_sun_3weeks.py`
- actual structure: browser workflow, clearly multi-step
- current state: **C**

Observed stages include:

- load credentials
- select target reservation
- open reservation list
- locate change entry
- prepare extension
- submit extension
- verify result

### 7. `timescar-ask-cancel-next24h-2300`
### 8. `timescar-ask-cancel-next24h-0000`
### 9. `timescar-ask-cancel-next24h-0100`
### 10. `timescar-ask-cancel-next24h-0700`
### 11. `timescar-ask-cancel-next24h-0800`

- delivery: `line`
- current script: `scripts/timescar/timescar_next24h_notice.py`
- actual structure: multi-step read workflow
- current state: **C**

Observed stages include:

- fetch reservations
- parse fetch output
- filter next-24h reservations
- render reminder or `NO_REPLY`

## Summary

Current cron jobs are no longer interpreted as:

- “news is single-step”
- “weather is single-step”
- “TimesCar is single-step”

More accurate summary:

- all current user-facing cron jobs in this bundle are externally wrapped by one `exec`
- but their actual execution structures are multi-step
- the important repo-managed ones are now observable enough for later scheduler migration

## Remaining Gap

These jobs are not yet native scheduler graph jobs.

They are:

- externally one cron run
- internally staged and observable

The next migration step is not “discover whether they are multi-step” anymore.
That question is now settled.

The next step is:

- move selected staged jobs from wrapper scripts into first-class native scheduler job types
