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

`openclaw-log-retention.timer` runs daily around 02:40 JST. Daily execution allows the 10 percent disk guard to react before the next monthly boundary.

## Verification

```text
systemctl status openclaw-log-retention.timer
systemctl status openclaw-log-retention.service
find /var/backups/openclaw-log-archive -type f
df -h /
```

## Rollback

Disable `openclaw-log-retention.timer`, remove its unit files and installed scripts, then run `systemctl daemon-reload`. Existing ZIP and journal archives can be retained or restored manually.
