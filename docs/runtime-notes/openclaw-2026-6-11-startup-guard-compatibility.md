# OpenClaw 2026.6.11 startup guard compatibility

Date: 2026-07-12

## Incident

After OpenClaw changed its generated runtime and memory plugin layout, the local agent society patch could no longer find its previous JavaScript anchor. The startup guard returned a failure from `ExecStartPre`, so systemd restarted the gateway every five seconds before the main process could start.

## Requirement change

Runtime patch drift must be reported as a degraded capability. It must not block the OpenClaw gateway from starting. The systemd drop-in also marks the custom guard as non-blocking.

The guard still fails for missing repository scripts, kernel bootstrap failures, and verification failures after a patch reports success. These conditions indicate a broken local deployment rather than an upstream layout change.

## Verification

1. The guard records an explicit compatibility warning when the runtime patch cannot be applied.
2. The gateway continues through startup.
3. The service becomes active and remains stable.
4. Model and channel checks run only after the gateway process is available.

## Rollback

Restore the previous guard script and systemd drop-in from version control, then run `systemctl daemon-reload` and restart `openclaw.service`.
