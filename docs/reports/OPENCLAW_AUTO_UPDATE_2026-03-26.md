# OpenClaw Auto Update

Date: 2026-03-26 (Asia/Tokyo)

## Goal

Move OpenClaw self-update out of the agent path and into a root-managed maintenance path.

## Deployed Components

- `/usr/local/lib/openclaw-maint/check_openclaw_update.sh`
- `/usr/local/lib/openclaw-maint/apply_openclaw_update.sh`
- `/etc/systemd/system/openclaw-update.service`
- `/etc/systemd/system/openclaw-update.timer`
- `/var/log/openclaw-maint`

## Timer

- schedule:
  - `06:20 JST`
- randomized delay:
  - `5m`

## Verified Result

- before:
  - `OpenClaw 2026.3.13`
- after:
  - `OpenClaw 2026.3.24`
- `openclaw.service` remained `active`

## Notes

- root owns package replacement under `/usr/lib/node_modules/openclaw`
- the agent may report updates, but root-side maintenance owns the actual upgrade and restart path
