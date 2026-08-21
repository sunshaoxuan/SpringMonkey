# OpenClaw log retention and disk protection

## Policy

1. Files modified in the current calendar month remain active and uncompressed.
2. Files from earlier months are appended to one ZIP archive per source and month, then removed after archive verification.
3. The previous month of `openclaw.service` journal is exported to a compressed monthly archive. Journald keeps approximately the current 35 days online.
4. When filesystem free space falls below 10 percent, the retention manager removes the oldest compressed log archive first and repeats until free space reaches the threshold or no log archive remains.
5. Recovery bundle temporary directories are removed on every exit, including failed archive creation. The recovery pruner also removes stale expanded directories.

## Managed sources

- `/var/lib/openclaw/.openclaw/logs`
- `/var/lib/openclaw/repos/SpringMonkey/implementation_run_logs`
- `/var/log/openclaw`
- `/var/log/openclaw-maint`
- `openclaw.service` journal export

Archives are stored under `/var/backups/openclaw-log-archive`.

## Schedule

The existing `openclaw-cron-failure-self-heal.timer` invokes the retention runner after each scan. A durable daily success marker makes the archive and disk guard execute at most once per calendar day. This path activates automatically after the repository sync and does not add, replace, disable, or reschedule any business cron job.

`openclaw-log-retention.timer` remains an optional dedicated schedule and runs daily around 02:40 JST when installed. Daily execution allows the 10 percent disk guard to react before the next monthly boundary.

## Verification

```text
systemctl status openclaw-log-retention.timer
systemctl status openclaw-log-retention.service
find /var/backups/openclaw-log-archive -type f
cat /var/lib/openclaw/.openclaw/workspace/agent_society_kernel/log_retention_run_state.json
df -h /
```

## Rollback

Disable `openclaw-log-retention.timer`, remove its unit files and installed scripts, then run `systemctl daemon-reload`. Existing ZIP and journal archives can be retained or restored manually.
