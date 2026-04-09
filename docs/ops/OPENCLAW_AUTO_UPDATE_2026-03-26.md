# OpenClaw Auto Update

Date: 2026-03-26 (Asia/Tokyo)

## Goal

Move OpenClaw self-update out of the agent path and into a root-managed maintenance path.

Reason:

- update discovery is safe for the agent
- package replacement under `/usr/lib/node_modules/openclaw` is not safely writable by the `openclaw` user
- automatic self-upgrade by the agent would mix task authority with runtime replacement authority

## Deployed Components

- script:
  - `/usr/local/lib/openclaw-maint/check_openclaw_update.sh`
- script:
  - `/usr/local/lib/openclaw-maint/apply_openclaw_update.sh`
- service:
  - `/etc/systemd/system/openclaw-update.service`
- timer:
  - `/etc/systemd/system/openclaw-update.timer`
- logs:
  - `/var/log/openclaw-maint`

## Timer

- daily schedule:
  - `06:20 JST`
- randomized delay:
  - `5m`

## Verified Result

- before:
  - `OpenClaw 2026.3.13`
- after:
  - `OpenClaw 2026.3.24`
- `openclaw.service` remained `active`

## Important Notes

- `openclaw update status --json` can include plugin log noise before the JSON body
- the maintenance script now strips leading log lines and parses the first JSON object
- update ownership remains root-side by design
- this path must not alter `frpc`, `tailscale`, `ssh`, or `docker`

## Operational Boundary

- `汤猴` may check for updates and report them
- root-side maintenance owns package replacement and post-update restart/self-check
