# Generic Cron Task Domain (2026-04)

Purpose: let `汤猴` create ordinary recurring jobs as real OpenClaw cron records instead of replying with a fake "already scheduled" message.

## Problem This Fix Addresses

Recent Discord weather-task attempts proved that the agent could:

- understand the request
- describe a plausible schedule
- claim success

but still fail to write any real cron job into `/var/lib/openclaw/.openclaw/cron/jobs.json`.

That means "natural-language confidence" is not sufficient evidence of task creation.

## Required Rule

For generic scheduled-task requests, the agent must not claim success unless machine evidence exists.

Accepted evidence:

1. `openclaw cron add` or `openclaw cron edit` returns success JSON for the intended job
2. the intended job exists in `/var/lib/openclaw/.openclaw/cron/jobs.json`
3. the stored `delivery.channel` and `delivery.to` match the requested target
4. optional stronger proof: `runuser -u openclaw -- env HOME=/var/lib/openclaw openclaw cron list --all --json` also shows the same job

If any of these checks fails, the agent must say task creation did not finish.

## Generic Job Writer

Use:

- `scripts/cron/upsert_generic_cron_job.py`

This script is the generic task-domain entry point for ordinary recurring jobs.

It uses the official Gateway CLI:

- `openclaw cron add`
- `openclaw cron edit`
- `openclaw cron rm`
- `openclaw cron list --all --json`

It supports:

- create or update a cron job by stable name
- store a full `agentTurn` payload
- set `delivery.channel` and `delivery.to`
- verify an existing job
- delete a job by name

## Usage Pattern

### Create or update

```bash
python3 /var/lib/openclaw/repos/SpringMonkey/scripts/cron/upsert_generic_cron_job.py \
  --name weather-report-jst-0700 \
  --expr "0 7 * * 1-5" \
  --tz Asia/Tokyo \
  --message-file /tmp/weather_report_prompt.txt \
  --delivery-channel discord \
  --delivery-to 1483636573235843072
```

### Verify

```bash
python3 /var/lib/openclaw/repos/SpringMonkey/scripts/cron/upsert_generic_cron_job.py \
  --name weather-report-jst-0700 \
  --verify-only
```

### Delete

```bash
python3 /var/lib/openclaw/repos/SpringMonkey/scripts/cron/upsert_generic_cron_job.py \
  --name weather-report-jst-0700 \
  --delete
```

## Delivery Rule

The agent must explicitly store:

- `delivery.channel`
- `delivery.to`
- `delivery.accountId`
- `delivery.mode`

Never assume "same channel" without checking the actual stored target.

## Website Rule

This task domain is generic. It must not hardcode a single website policy for all future tasks.

Allowed pattern:

- use the website or source explicitly requested by the user
- or use a source discovered during the task itself
- then write that source rule into the job payload or companion instructions

Forbidden pattern:

- permanently restrict all future tasks to one source because one previous task used it

## Recommended Post-Create Check

After writing a job:

1. verify with `openclaw cron list --all --json` under the `openclaw` user context
2. verify by job name in `jobs.json`
3. only then tell the user the task is created

Current runtime note:

- `openclaw cron list --json` may still emit noisy `slack` config warnings on `stderr`
- when parsing its JSON output in scripts, redirect `stderr` away from the parser
- do not treat that warning as evidence that cron creation failed if `stdout` is valid JSON and the job is visible

## Recovery Note

If generic scheduled tasks start "sounding successful" but no job appears:

- inspect the current session logs
- inspect `jobs.json`
- check whether the agent actually used `upsert_generic_cron_job.py`
- do not trust the conversational reply alone
